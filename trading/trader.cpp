// trader.cpp
// Reads malaysia_agriculture_companies.csv, looks up each company's live
// Bursa Malaysia price on Google Finance, prints it, and writes
// malaysia_agriculture_live.csv.
//
// Build:  g++ -std=c++11 trader.cpp -o trader -lcurl
// Run:    ./trader

#include <curl/curl.h>

#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

const char* const INPUT_FILE  = "malaysia_agriculture_companies.csv";
const char* const OUTPUT_FILE = "malaysia_agriculture_live.csv";

// Column positions in the CSV
const std::size_t COL_NAME     = 0;
const std::size_t COL_TICKER   = 1;   // Bursa ticker, e.g. SDG
const std::size_t COL_YAHOO    = 2;   // "N/A" marks delisted/private companies
const std::size_t COL_PRODUCTS = 6;   // always written back in quotes
const std::size_t COL_PRICE    = 8;
const std::size_t NUM_COLUMNS  = 9;

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
// The URL is built from small pieces so formatters cannot mangle it.
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
    double price;       // -1.0 when not found
    double change;      // change since previous close, in RM
    double changePct;   // same change, in percent
};

// Google embeds the quote in the page like this:
//   ["SDG","KLSE"],"SD Guthrie Bhd",0,"MYR",[6.04,-0.11,-1.79,...
//                                           price, change, change %
// The ["SDG","KLSE"] part also appears in other places (earnings, related
// stocks), so each occurrence is checked until one has this exact shape.
Quote extractQuote(const std::string& html, const std::string& ticker) {
    Quote q;
    q.price = -1.0;
    q.change = 0.0;
    q.changePct = 0.0;

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

int main() {
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
        if (row.size() < NUM_COLUMNS - 1) {
            std::cerr << "Warning: skipping malformed line: " << line << "\n";
            continue;
        }
        row.resize(NUM_COLUMNS);
        rows.push_back(row);
    }
    infile.close();

    // ---- 2. Fetch a price for each company ----
    curl_global_init(CURL_GLOBAL_DEFAULT);
    CURL* curl = curl_easy_init();
    if (!curl) {
        std::cerr << "Error: could not start libcurl\n";
        return 1;
    }

    std::cout << "Fetching live prices for " << rows.size() << " companies...\n\n";
    std::cout << "        Company                               Ticker        Price  Change\n";
    std::cout << "----------------------------------------------------------------------------------\n";
    std::size_t priced = 0;

    for (std::size_t i = 0; i < rows.size(); ++i) {
        std::vector<std::string>& row = rows.at(i);
        const std::string ticker = row.at(COL_TICKER);
        const bool listed = row.at(COL_YAHOO) != "N/A" && !row.at(COL_YAHOO).empty();
        Quote q;
        q.price = -1.0;
        q.change = 0.0;
        q.changePct = 0.0;

        if (listed) {
            std::string html;
            const long status = fetchGooglePage(curl, ticker, html);
            q = extractQuote(html, ticker);
            if (q.price <= 0.0) {
                std::string start = html.substr(0, 150);
                for (std::size_t k = 0; k < start.size(); ++k) {
                    if (start.at(k) == '\n' || start.at(k) == '\r') start.at(k) = ' ';
                }
                std::cerr << "    No price for " << ticker << ": HTTP " << status
                          << " | " << start << "\n";
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(300));
        }

        row.at(COL_PRICE) = formatPrice(q.price);

        std::cout << "[" << std::setw(2) << (i + 1) << "/" << rows.size() << "] "
                  << std::left << std::setw(38) << row.at(COL_NAME)
                  << std::setw(9) << (listed ? ticker : "N/A") << std::right;
        if (q.price > 0.0) {
            ++priced;
            std::cout << "RM " << std::setw(7) << row.at(COL_PRICE) << "  " << formatChange(q) << "\n";
        } else {
            std::cout << "N/A\n";
        }
    }

    curl_easy_cleanup(curl);
    curl_global_cleanup();

    // ---- 3. Write the updated CSV ----
    std::ofstream outfile(OUTPUT_FILE);
    if (!outfile.is_open()) {
        std::cerr << "Error: could not write " << OUTPUT_FILE << "\n";
        return 1;
    }
    outfile << header << "\n";
    for (std::size_t i = 0; i < rows.size(); ++i) {
        const std::vector<std::string>& row = rows.at(i);
        for (std::size_t c = 0; c < NUM_COLUMNS; ++c) {
            if (c > 0) outfile << ",";
            if (c == COL_PRODUCTS) outfile << "\"" << row.at(c) << "\"";
            else outfile << row.at(c);
        }
        outfile << "\n";
    }
    outfile.close();

    std::cout << "\nDone: " << priced << " of " << rows.size() << " priced.\n"
              << "Saved to " << OUTPUT_FILE << "\n";
    return 0;
}
