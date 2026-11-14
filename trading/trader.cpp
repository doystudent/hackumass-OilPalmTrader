// Build:  g++ -std=c++11 trader.cpp -o trader -lcurl -pthread
// Run:    ./trader                       fetch live prices for every company
//         ./trader --soil <file>         list companies that fit a soil report
//                                        (file is written by ai/soil_analyzer.py)

#include <curl/curl.h>

#include <algorithm>
#include <atomic>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

const char* const INPUT_FILE  = "malaysia_agriculture_companies.csv";
const char* const OUTPUT_FILE = "malaysia_agriculture_live.csv";
const char* const RULES_FILE  = "soil_rules.csv";

// Column positions in the CSV
const std::size_t COL_NAME     = 0;
const std::size_t COL_TICKER   = 1;
const std::size_t COL_PRODUCTS = 2;
const std::size_t NUM_COLUMNS  = 3;

// How many Google Finance pages to download at the same time.
const std::size_t MAX_DOWNLOADS = 25;

// Removes spaces, tabs, \r and \n from both ends.
std::string trim(const std::string& s) {
    const std::string blanks = " \t\r\n";
    const std::size_t start = s.find_first_not_of(blanks);
    if (start == std::string::npos) return "";
    const std::size_t end = s.find_last_not_of(blanks);
    return s.substr(start, end - start + 1);
}

// Splits one CSV line, keeping commas that are inside "..." together.
std::vector<std::string> parseCSVLine(const std::string& line) {
    std::vector<std::string> fields;
    std::string field;
    bool inQuotes = false;
    for (std::size_t i = 0; i < line.size(); ++i) {
        const char c = line.at(i);
        if (c == '"') {
            inQuotes = !inQuotes;
        } else if (c == ',' && !inQuotes) {
            fields.push_back(trim(field));
            field.clear();
        } else {
            field += c;
        }
    }
    fields.push_back(trim(field));
    return fields;
}

// Companies that are no longer traded carry "N/A" in the ticker column instead.
bool isTradedTicker(const std::string& ticker) {
    if (ticker.empty() || ticker == "N/A") return false;
    return ticker.find("elisted") == std::string::npos;
}

std::string formatPrice(double price) {
    if (price <= 0.0) return "N/A";
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(3) << price;
    return oss.str();
}

std::size_t writeCallback(void* data, std::size_t size, std::size_t nmemb, void* userp) {
    static_cast<std::string*>(userp)->append(static_cast<char*>(data), size * nmemb);
    return size * nmemb;
}

// Downloads the Google Finance page for a Bursa ticker (e.g. SDG:KLSE).
// Returns the HTTP status code (0 if the request itself failed).
long fetchGooglePage(CURL* curl, const std::string& ticker, std::string& body) {
    std::string url;
    url += "https";
    url += "://";
    url += "www";
    url += ".google";
    url += ".com";
    url += "/finance";
    url += "/quote/";
    url += ticker;
    url += ":KLSE";
    url += "?hl=en";

    body.clear();
    curl_easy_reset(curl);
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_USERAGENT,
                     "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36");
    curl_easy_setopt(curl, CURLOPT_COOKIE, "CONSENT=YES+");
    curl_easy_setopt(curl, CURLOPT_IPRESOLVE, CURL_IPRESOLVE_V4);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(curl, CURLOPT_ACCEPT_ENCODING, "");
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 20L);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &body);

    long status = 0;
    if (curl_easy_perform(curl) == CURLE_OK) {
        curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);
    }
    return status;
}

struct Quote {
    double price; // -1.0 when not found
    double change;
    double changePct;
};

Quote emptyQuote() {
    Quote q;
    q.price = -1.0;
    q.change = 0.0;
    q.changePct = 0.0;
    return q;
}

// Google embeds the quote in the page like this:
//   ["SDG","KLSE"],"SD Guthrie Bhd",0,"MYR",[6.04,-0.11,-1.79,...
//                                           price, change, change %
// The ["SDG","KLSE"] part also appears in other places (earnings, related
// stocks), so each occurrence is checked until one has this exact shape.
Quote extractQuote(const std::string& html, const std::string& ticker) {
    Quote q = emptyQuote();
    const std::string key = "[\"" + ticker + "\",\"KLSE\"],\"";
    const std::string marker = "\",0,\"MYR\",[";

    std::size_t pos = html.find(key);
    while (pos != std::string::npos) {
        const std::size_t nameEnd = html.find('"', pos + key.size());
        if (nameEnd != std::string::npos &&
            html.compare(nameEnd, marker.size(), marker) == 0) {
            // Read "price,change,percent" by swapping the commas for spaces.
            std::string numbers = html.substr(nameEnd + marker.size(), 60);
            for (std::size_t k = 0; k < numbers.size(); ++k) {
                if (numbers.at(k) == ',') numbers.at(k) = ' ';
            }
            std::istringstream iss(numbers);
            double price = 0.0;
            if (iss >> price && price > 0.0) {
                q.price = price;
                if (!(iss >> q.change >> q.changePct)) {
                    q.change = 0.0;
                    q.changePct = 0.0;
                }
                return q;
            }
        }
        pos = html.find(key, pos + 1);
    }
    return q;
}

// e.g. "-0.110 (-1.79%)" or "+0.170 (+3.20%)"
std::string formatChange(const Quote& q) {
    std::ostringstream oss;
    oss << std::showpos << std::fixed << std::setprecision(3) << q.change
        << " (" << std::setprecision(2) << q.changePct << "%)";
    return oss.str();
}

// Each worker owns its own libcurl handle and takes the next unprocessed
// company until none are left. Every company writes only to its own slot
// in quotes/errors, so the workers never touch the same element.
void downloadWorker(std::atomic<std::size_t>& nextIndex,
                    const std::vector<std::vector<std::string> >& rows,
                    std::vector<Quote>& quotes,
                    std::vector<std::string>& errors) {
    CURL* curl = curl_easy_init();
    if (!curl) return;

    for (;;) {
        const std::size_t i = nextIndex++;
        if (i >= rows.size()) break;

        const std::string ticker = rows.at(i).at(COL_TICKER);
        if (!isTradedTicker(ticker)) continue;

        std::string html;
        const long status = fetchGooglePage(curl, ticker, html);
        quotes.at(i) = extractQuote(html, ticker);

        if (quotes.at(i).price <= 0.0) {
            std::string start = html.substr(0, 150);
            for (std::size_t k = 0; k < start.size(); ++k) {
                if (start.at(k) == '\n' || start.at(k) == '\r') start.at(k) = ' ';
            }
            std::ostringstream msg;
            msg << "    No price for " << ticker << ": HTTP " << status
                << " | " << start << "\n";
            errors.at(i) = msg.str();
        }
    }
    curl_easy_cleanup(curl);
}

int runPriceFetch() {
    // ---- 1. Read the CSV ----
    std::ifstream infile(INPUT_FILE);
    if (!infile.is_open()) {
        std::cerr << "Error: could not open " << INPUT_FILE << "\n";
        return 1;
    }

    std::string header;
    std::getline(infile, header);
    header = trim(header);

    std::vector<std::vector<std::string> > rows;
    std::string line;
    while (std::getline(infile, line)) {
        if (trim(line).empty()) continue;
        std::vector<std::string> row = parseCSVLine(line);
        if (row.size() < NUM_COLUMNS) {
            std::cerr << "Warning: skipping malformed line: " << line << "\n";
            continue;
        }
        row.resize(NUM_COLUMNS);
        rows.push_back(row);
    }
    infile.close();

    // ---- 2. Fetch prices, several at a time ----
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        std::cerr << "Error: could not start libcurl\n";
        return 1;
    }

    std::vector<Quote> quotes(rows.size(), emptyQuote());
    std::vector<std::string> errors(rows.size());
    std::atomic<std::size_t> nextIndex(0);

    const std::size_t numThreads = rows.size() < MAX_DOWNLOADS ? rows.size() : MAX_DOWNLOADS;
    std::cout << "Fetching live prices for " << rows.size() << " companies ("
              << numThreads << " at a time)...\n";

    std::vector<std::thread> workers;
    for (std::size_t t = 0; t < numThreads; ++t) {
        workers.emplace_back(downloadWorker, std::ref(nextIndex), std::cref(rows),
                             std::ref(quotes), std::ref(errors));
    }
    for (std::size_t t = 0; t < workers.size(); ++t) {
        workers.at(t).join();
    }

    curl_global_cleanup();

    // ---- 3. Print the results in the original order ----
    std::size_t productsWidth = 8;
    for (std::size_t i = 0; i < rows.size(); ++i) {
        if (rows.at(i).at(COL_PRODUCTS).size() > productsWidth) {
            productsWidth = rows.at(i).at(COL_PRODUCTS).size();
        }
    }
    productsWidth += 2;

    std::cout << "\n" << std::left << std::setw(8) << "" << std::setw(38) << "Company"
              << std::setw(static_cast<int>(productsWidth)) << "Products"
              << std::setw(9) << "Ticker" << "     Price  Change\n" << std::right;
    std::cout << std::string(8 + 38 + productsWidth + 9 + 28, '-') << "\n";

    std::vector<std::string> prices;
    std::size_t priced = 0;

    for (std::size_t i = 0; i < rows.size(); ++i) {
        const std::vector<std::string>& row = rows.at(i);
        const std::string& ticker = row.at(COL_TICKER);
        const bool traded = isTradedTicker(ticker);
        const Quote& q = quotes.at(i);

        if (!errors.at(i).empty()) std::cerr << errors.at(i);

        prices.push_back(formatPrice(q.price));

        std::cout << "[" << std::setw(2) << (i + 1) << "/" << rows.size() << "] "
                  << std::left << std::setw(38) << row.at(COL_NAME)
                  << std::setw(static_cast<int>(productsWidth)) << row.at(COL_PRODUCTS)
                  << std::setw(9) << (traded ? ticker : "N/A") << std::right;
        if (q.price > 0.0) {
            ++priced;
            std::cout << "RM " << std::setw(7) << prices.back() << "  " << formatChange(q) << "\n";
        } else {
            std::cout << "N/A\n";
        }
    }

    // ---- 4. Write the updated CSV ----
    std::ofstream outfile(OUTPUT_FILE);
    if (!outfile.is_open()) {
        std::cerr << "Error: could not write " << OUTPUT_FILE << "\n";
        return 1;
    }
    outfile << header << ",Live Price (MYR)\n";
    for (std::size_t i = 0; i < rows.size(); ++i) {
        const std::vector<std::string>& row = rows.at(i);
        outfile << row.at(COL_NAME) << ","
                << row.at(COL_TICKER) << ","
                << "\"" << row.at(COL_PRODUCTS) << "\","
                << prices.at(i) << "\n";
    }
    outfile.close();

    std::cout << "\nDone: " << priced << " of " << rows.size() << " priced.\n"
              << "Saved to " << OUTPUT_FILE << "\n";
    return 0;
}

// ===================== Soil report -> companies =====================
//
// ai/soil_analyzer.py writes the soil report as plain "key=value" lines:
//   moisture=dry
//   texture=sandy
//   drainage=good
//   health=4
//   organic_matter_pct=1.5
//   ph=5.2
// The report is turned into conditions ("dry", "acidic", ...), and
// soil_rules.csv says which product keywords go with each condition.

// Numeric cut-offs used to turn the report's numbers into conditions.
const double HEALTH_POOR_MAX    = 4.0;   // health <= this  -> poor_health
const double HEALTH_GOOD_MIN    = 7.0;   // health >= this  -> healthy
const double PH_ACIDIC_BELOW    = 5.0;   // ph < this       -> acidic
const double PH_ALKALINE_ABOVE  = 7.5;   // ph > this       -> alkaline
const double ORGANIC_LOW_BELOW  = 2.0;   // organic % < this -> low_organic

std::string toLower(std::string s) {
    for (std::size_t i = 0; i < s.size(); ++i) {
        s.at(i) = static_cast<char>(std::tolower(static_cast<unsigned char>(s.at(i))));
    }
    return s;
}

std::vector<std::string> split(const std::string& s, char sep) {
    std::vector<std::string> parts;
    std::istringstream iss(s);
    std::string part;
    while (std::getline(iss, part, sep)) {
        part = trim(part);
        if (!part.empty()) parts.push_back(part);
    }
    return parts;
}

// Reads "key=value" lines. Keys and values are lower-cased.
bool readSoilReport(const std::string& path, std::map<std::string, std::string>& report) {
    std::ifstream in(path.c_str());
    if (!in.is_open()) return false;
    std::string line;
    while (std::getline(in, line)) {
        const std::size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        report[toLower(trim(line.substr(0, eq)))] = toLower(trim(line.substr(eq + 1)));
    }
    return true;
}

// Reads a number from the report; false if the key is missing or not numeric.
bool reportNumber(const std::map<std::string, std::string>& report,
                  const std::string& key, double& value) {
    const std::map<std::string, std::string>::const_iterator it = report.find(key);
    if (it == report.end()) return false;
    std::istringstream iss(it->second);
    return static_cast<bool>(iss >> value);
}

std::vector<std::string> soilConditions(const std::map<std::string, std::string>& report) {
    std::vector<std::string> conditions;
    std::map<std::string, std::string>::const_iterator it;

    it = report.find("moisture");                       // dry | moist | wet
    if (it != report.end() && !it->second.empty()) conditions.push_back(it->second);

    it = report.find("texture");                        // sandy | silty | clayey | loamy
    if (it != report.end() && !it->second.empty()) conditions.push_back(it->second);

    it = report.find("drainage");                       // poor | moderate | good
    if (it != report.end() && it->second == "poor") conditions.push_back("poor_drainage");

    double n = 0.0;
    if (reportNumber(report, "health", n)) {
        if (n <= HEALTH_POOR_MAX) conditions.push_back("poor_health");
        else if (n >= HEALTH_GOOD_MIN) conditions.push_back("healthy");
    }
    if (reportNumber(report, "ph", n)) {
        if (n < PH_ACIDIC_BELOW) conditions.push_back("acidic");
        else if (n > PH_ALKALINE_ABOVE) conditions.push_back("alkaline");
    }
    if (reportNumber(report, "organic_matter_pct", n) && n < ORGANIC_LOW_BELOW) {
        conditions.push_back("low_organic");
    }
    return conditions;
}

struct SoilRule {
    std::string condition;
    std::vector<std::string> keywords;
    std::string reason;
};

bool readSoilRules(std::vector<SoilRule>& rules) {
    std::ifstream in(RULES_FILE);
    if (!in.is_open()) return false;
    std::string line;
    std::getline(in, line);
    while (std::getline(in, line)) {
        if (trim(line).empty()) continue;
        const std::vector<std::string> f = parseCSVLine(line);
        if (f.size() < 3) {
            std::cerr << "Warning: skipping malformed rule: " << line << "\n";
            continue;
        }
        SoilRule rule;
        rule.condition = toLower(f.at(0));
        rule.keywords = split(toLower(f.at(1)), ';');
        rule.reason = f.at(2);
        rules.push_back(rule);
    }
    return true;
}

struct Match {
    std::vector<std::string> row;   // name, ticker, products
    std::string matched;            // soil conditions that fit, e.g. "moist, loamy"
    std::size_t numMatched;
    std::size_t order;
};

bool betterMatch(const Match& a, const Match& b) {
    if (a.numMatched != b.numMatched) return a.numMatched > b.numMatched;
    return a.order < b.order;
}

int runSoilMatch(const std::string& reportPath) {
    // ---- 1. Soil report -> conditions ----
    std::map<std::string, std::string> report;
    if (!readSoilReport(reportPath, report)) {
        std::cerr << "Error: could not open soil report " << reportPath << "\n";
        return 1;
    }
    const std::vector<std::string> conditions = soilConditions(report);
    if (conditions.empty()) {
        std::cerr << "Error: no usable soil values in " << reportPath << "\n";
        return 1;
    }

    std::vector<SoilRule> rules;
    if (!readSoilRules(rules)) {
        std::cerr << "Error: could not open " << RULES_FILE << "\n";
        return 1;
    }

    // ---- 2. Find the companies whose products fit the conditions ----
    std::ifstream infile(INPUT_FILE);
    if (!infile.is_open()) {
        std::cerr << "Error: could not open " << INPUT_FILE << "\n";
        return 1;
    }
    std::string line;
    std::getline(infile, line);

    std::vector<Match> matches;
    std::size_t order = 0;
    while (std::getline(infile, line)) {
        if (trim(line).empty()) continue;
        std::vector<std::string> row = parseCSVLine(line);
        if (row.size() < NUM_COLUMNS) continue;
        row.resize(NUM_COLUMNS);
        ++order;
        if (!isTradedTicker(row.at(COL_TICKER))) continue;   // cannot invest in these

        const std::string products = toLower(row.at(COL_PRODUCTS));
        Match m;
        m.row = row;
        m.order = order;
        m.numMatched = 0;
        for (std::size_t c = 0; c < conditions.size(); ++c) {
            bool fits = false;
            for (std::size_t r = 0; r < rules.size() && !fits; ++r) {
                if (rules.at(r).condition != conditions.at(c)) continue;
                for (std::size_t k = 0; k < rules.at(r).keywords.size(); ++k) {
                    if (products.find(rules.at(r).keywords.at(k)) != std::string::npos) {
                        fits = true;
                        break;
                    }
                }
            }
            if (fits) {
                if (m.numMatched > 0) m.matched += ", ";
                m.matched += conditions.at(c);
                ++m.numMatched;
            }
        }
        if (m.numMatched > 0) matches.push_back(m);
    }
    infile.close();
    std::sort(matches.begin(), matches.end(), betterMatch);

    std::cout << "Soil conditions:";
    for (std::size_t c = 0; c < conditions.size(); ++c) {
        std::cout << (c > 0 ? ", " : " ") << conditions.at(c);
    }
    std::cout << "\n";

    if (matches.empty()) {
        std::cout << "\nNo companies match these conditions.\n";
        return 0;
    }

    // ---- 3. Fetch live prices for the matched companies ----
    std::vector<std::vector<std::string> > rows;
    for (std::size_t i = 0; i < matches.size(); ++i) rows.push_back(matches.at(i).row);

    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        std::cerr << "Error: could not start libcurl\n";
        return 1;
    }
    std::vector<Quote> quotes(rows.size(), emptyQuote());
    std::vector<std::string> errors(rows.size());
    std::atomic<std::size_t> nextIndex(0);

    const std::size_t numThreads = rows.size() < MAX_DOWNLOADS ? rows.size() : MAX_DOWNLOADS;
    std::cout << "Fetching live prices for " << rows.size() << " matching companies ("
              << numThreads << " at a time)...\n";

    std::vector<std::thread> workers;
    for (std::size_t t = 0; t < numThreads; ++t) {
        workers.emplace_back(downloadWorker, std::ref(nextIndex), std::cref(rows),
                             std::ref(quotes), std::ref(errors));
    }
    for (std::size_t t = 0; t < workers.size(); ++t) {
        workers.at(t).join();
    }
    curl_global_cleanup();

    // ---- 4. Print: same table as the price fetch, plus a Matched column ----
    std::size_t productsWidth = 8;
    for (std::size_t i = 0; i < rows.size(); ++i) {
        if (rows.at(i).at(COL_PRODUCTS).size() > productsWidth) {
            productsWidth = rows.at(i).at(COL_PRODUCTS).size();
        }
    }
    productsWidth += 2;
    const int changeWidth = 18;

    std::ostringstream total;
    total << rows.size();
    const std::size_t countWidth = 5 + total.str().size();

    std::cout << "\n" << std::left << std::setw(static_cast<int>(countWidth)) << ""
              << std::setw(38) << "Company"
              << std::setw(static_cast<int>(productsWidth)) << "Products"
              << std::setw(9) << "Ticker" << "     Price  "
              << std::setw(changeWidth) << "Change" << "Matched\n" << std::right;
    std::cout << std::string(countWidth + 38 + productsWidth + 9 + 12 + changeWidth + 22, '-')
              << "\n";

    std::size_t priced = 0;
    for (std::size_t i = 0; i < rows.size(); ++i) {
        const std::vector<std::string>& row = rows.at(i);
        const Quote& q = quotes.at(i);

        if (!errors.at(i).empty()) std::cerr << errors.at(i);

        std::cout << "[" << std::setw(2) << (i + 1) << "/" << rows.size() << "] "
                  << std::left << std::setw(38) << row.at(COL_NAME)
                  << std::setw(static_cast<int>(productsWidth)) << row.at(COL_PRODUCTS)
                  << std::setw(9) << row.at(COL_TICKER) << std::right;
        if (q.price > 0.0) {
            ++priced;
            std::cout << "RM " << std::setw(7) << formatPrice(q.price) << "  "
                      << std::left << std::setw(changeWidth) << formatChange(q) << std::right;
        } else {
            std::cout << std::left << std::setw(12 + changeWidth) << "N/A" << std::right;
        }
        std::cout << matches.at(i).matched << "\n";
    }

    std::cout << "\nDone: " << matches.size() << " of " << order << " companies match, "
              << priced << " priced.\n";
    return 0;
}

int main(int argc, char* argv[]) {
    if (argc == 3 && std::string(argv[1]) == "--soil") {
        return runSoilMatch(argv[2]);
    }
    if (argc != 1) {
        std::cerr << "Usage: " << argv[0] << "                 fetch live prices\n"
                  << "       " << argv[0] << " --soil <file>   companies for a soil report\n";
        return 1;
    }
    return runPriceFetch();
}
