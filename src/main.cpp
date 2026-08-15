#include "neurochess/uci/uci_loop.h"

#include <iostream>

int main() {
    return neurochess::uci::run(std::cin, std::cout);
}
