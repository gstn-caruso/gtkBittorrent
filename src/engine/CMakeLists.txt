cmake_minimum_required(VERSION 3.16)

if (CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    project(GtkBittorrentEngineClient LANGUAGES CXX)
    include(CTest)
endif()

find_package(CURL 8.4 REQUIRED)
find_package(nlohmann_json 3.11 REQUIRED)

add_library(gtkbittorrent_engine_client STATIC client.cpp)
target_compile_features(gtkbittorrent_engine_client PUBLIC cxx_std_20)
target_include_directories(gtkbittorrent_engine_client PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/..")
target_link_libraries(gtkbittorrent_engine_client PRIVATE CURL::libcurl nlohmann_json::nlohmann_json)
set_target_properties(gtkbittorrent_engine_client PROPERTIES AUTOMOC OFF AUTORCC OFF CXX_EXTENSIONS OFF)

if (BUILD_TESTING)
    find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
    add_executable(engineclient_probe "../../test/engineclient_probe.cpp")
    target_link_libraries(engineclient_probe PRIVATE gtkbittorrent_engine_client nlohmann_json::nlohmann_json)
    set_target_properties(engineclient_probe PROPERTIES AUTOMOC OFF AUTORCC OFF CXX_EXTENSIONS OFF)
    add_test(NAME testengineclient
        COMMAND "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/../../test/testengineclient.py"
            --probe "$<TARGET_FILE:engineclient_probe>"
    )
    set_tests_properties(testengineclient PROPERTIES LABELS "engine;integration" TIMEOUT 60)
    set(ENGINE_TEST_BINARY "" CACHE FILEPATH "Optional real headless engine for client integration tests")
    if (ENGINE_TEST_BINARY)
        add_test(NAME testengineclient_session
            COMMAND "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/../../test/testengineclient.py"
                --probe "$<TARGET_FILE:engineclient_probe>" --engine "${ENGINE_TEST_BINARY}"
                TestRealEngineClient -v
        )
        set_tests_properties(testengineclient_session PROPERTIES LABELS "engine;integration;session" TIMEOUT 60)
    endif()
endif()
