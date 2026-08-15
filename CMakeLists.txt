cmake_minimum_required(VERSION 3.20)
project(NeuroChess VERSION 0.15.0 LANGUAGES CXX)

option(NEUROCHESS_BUILD_TESTS "Build NeuroChess tests" ON)
option(NEUROCHESS_ENABLE_WARNINGS "Enable strict compiler warnings" ON)
option(NEUROCHESS_BUILD_BENCHMARKS "Build NeuroChess benchmark tools" ON)
option(NEUROCHESS_ENABLE_ONNX "Enable ONNX Runtime neural inference" OFF)
set(ONNXRUNTIME_ROOT "" CACHE PATH "Path to extracted ONNX Runtime package")

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(neurochess_engine
    src/core/engine_info.cpp
    src/core/board.cpp
    src/core/move.cpp
    src/core/move_generator.cpp
    src/core/zobrist.cpp
    src/nn/neural_evaluator.cpp
    src/search/searcher.cpp
    src/search/evaluator.cpp
    src/search/transposition_table.cpp
    src/uci/uci_loop.cpp
)

target_include_directories(neurochess_engine
    PUBLIC
        ${PROJECT_SOURCE_DIR}/include
)

if(NEUROCHESS_ENABLE_ONNX)
    if(NOT ONNXRUNTIME_ROOT)
        message(FATAL_ERROR "NEUROCHESS_ENABLE_ONNX=ON requires -DONNXRUNTIME_ROOT=<onnxruntime package>")
    endif()
    target_compile_definitions(neurochess_engine PRIVATE NEUROCHESS_ENABLE_ONNX=1)
    target_include_directories(neurochess_engine PRIVATE ${ONNXRUNTIME_ROOT}/include)
    find_library(ONNXRUNTIME_LIBRARY onnxruntime PATHS ${ONNXRUNTIME_ROOT}/lib REQUIRED NO_DEFAULT_PATH)
    target_link_libraries(neurochess_engine PRIVATE ${ONNXRUNTIME_LIBRARY})
endif()

if(NEUROCHESS_ENABLE_WARNINGS)
    if(MSVC)
        target_compile_options(neurochess_engine PRIVATE /W4 /permissive-)
    else()
        target_compile_options(neurochess_engine PRIVATE -Wall -Wextra -Wpedantic)
    endif()
endif()

add_executable(neurochess src/main.cpp)
target_link_libraries(neurochess PRIVATE neurochess_engine)

if(NEUROCHESS_BUILD_TESTS)
    enable_testing()
    add_executable(neurochess_tests tests/smoke_tests.cpp)
    target_link_libraries(neurochess_tests PRIVATE neurochess_engine)
    add_test(NAME neurochess_smoke COMMAND neurochess_tests)

    add_executable(neurochess_board_tests tests/board_tests.cpp)
    target_link_libraries(neurochess_board_tests PRIVATE neurochess_engine)
    add_test(NAME neurochess_board COMMAND neurochess_board_tests)

    add_executable(neurochess_movegen_tests tests/movegen_tests.cpp)
    target_link_libraries(neurochess_movegen_tests PRIVATE neurochess_engine)
    add_test(NAME neurochess_movegen COMMAND neurochess_movegen_tests)

    add_executable(neurochess_perft_tests tests/perft_tests.cpp)
    target_link_libraries(neurochess_perft_tests PRIVATE neurochess_engine)
    add_test(NAME neurochess_perft COMMAND neurochess_perft_tests)

    add_executable(neurochess_zobrist_tests tests/zobrist_tests.cpp)
    target_link_libraries(neurochess_zobrist_tests PRIVATE neurochess_engine)
    add_test(NAME neurochess_zobrist COMMAND neurochess_zobrist_tests)

    add_executable(neurochess_evaluator_tests tests/evaluator_tests.cpp)
    target_link_libraries(neurochess_evaluator_tests PRIVATE neurochess_engine)
    add_test(NAME neurochess_evaluator COMMAND neurochess_evaluator_tests)

    add_executable(neurochess_neural_evaluator_tests tests/neural_evaluator_tests.cpp)
    target_link_libraries(neurochess_neural_evaluator_tests PRIVATE neurochess_engine)
    add_test(NAME neurochess_neural_evaluator COMMAND neurochess_neural_evaluator_tests)

    if(NEUROCHESS_ENABLE_ONNX)
        add_executable(neurochess_neural_inference_smoke tests/neural_inference_smoke.cpp)
        target_link_libraries(neurochess_neural_inference_smoke PRIVATE neurochess_engine)
    endif()

    add_executable(neurochess_search_tests tests/search_tests.cpp)
    target_link_libraries(neurochess_search_tests PRIVATE neurochess_engine)
    add_test(NAME neurochess_search COMMAND neurochess_search_tests)

    add_executable(neurochess_search_optimization_tests tests/search_optimization_tests.cpp)
    target_link_libraries(neurochess_search_optimization_tests PRIVATE neurochess_engine)
    add_test(NAME neurochess_search_optimizations COMMAND neurochess_search_optimization_tests)

    add_executable(neurochess_uci_tests tests/uci_tests.cpp)
    target_link_libraries(neurochess_uci_tests PRIVATE neurochess_engine)
    add_test(NAME neurochess_uci COMMAND neurochess_uci_tests)

    find_package(Python3 COMPONENTS Interpreter QUIET)
    if(Python3_Interpreter_FOUND)
        add_test(
            NAME neurochess_match_runner
            COMMAND ${Python3_EXECUTABLE} -m unittest discover -s ${PROJECT_SOURCE_DIR}/tests/python -p "test_*.py"
        )
    endif()
endif()

if(NEUROCHESS_BUILD_BENCHMARKS)
    add_executable(neurochess_search_benchmark benchmarks/search_benchmark.cpp)
    target_link_libraries(neurochess_search_benchmark PRIVATE neurochess_engine)
endif()
