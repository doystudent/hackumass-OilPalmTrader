#include <iostream>
#include <string>
#include <cpr/cpr.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

// Replace with your Alpaca Paper Trading credentials
const std::string API_KEY = "PKXFZKH45G6GAVTKN2X4CR7KXJ";
const std::string API_SECRET = "8zmzf5ER3m6a2fqCoMLfPCUtxYfJfhYbgs16jS2Fq7dP";
const std::string BASE_URL = "https://alpaca.markets";

void executeOrder(const std::string& symbol, int qty, const std::string& side) {
    // 1. Construct the JSON payload
    json orderPayload = {
        {"symbol", symbol},
        {"qty", qty},
        {"side", side},          // "buy" or "sell"
        {"type", "market"},      // Execute immediately at market price
        {"time_in_force", "gtc"} // Good 'til canceled
    };

    // 2. Send the HTTP POST request
    cpr::Response r = cpr::Post(
        cpr::Url{BASE_URL},
        cpr::Header{
            {"APCA-API-KEY-ID", API_KEY},
            {"APCA-API-SECRET-KEY", API_SECRET},
            {"Content-Type", "application/json"}
        },
        cpr::Body{orderPayload.dump()}
    );

    // 3. Handle the response
    if (r.status_code == 200 || r.status_code == 201) {
        std::cout << "[SUCCESS] Order placed for " << qty << " shares of " << symbol << " (" << side << ").\n";
        std::cout << "Response: " << r.text << "\n";
    } else {
        std::cerr << "[ERROR] Failed to place order. HTTP Status: " << r.status_code << "\n";
        std::cerr << "Details: " << r.text << "\n";
    }
}

int main(int argc, char* argv[]) {
    // Expecting command-line arguments: ./trader <SYMBOL> <QTY> <SIDE>
    // Example: ./trader DBA 5 buy
    if (argc != 4) {
        std::cerr << "Usage: " << argv[0] << " <SYMBOL> <QTY> <BUY/SELL>\n";
        return 1;
    }

    std::string symbol = argv[1];
    int qty = std::stoi(argv[2]);
    std::string side = argv[3];

    executeOrder(symbol, qty, side);
    return 0;
}

