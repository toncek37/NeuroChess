#pragma once

#include <iosfwd>

namespace neurochess::uci {

// Runs the Universal Chess Interface command loop. Search commands execute on
// a worker thread so the GUI can issue "stop" while thinking.
int run(std::istream& in, std::ostream& out);

} // namespace neurochess::uci
