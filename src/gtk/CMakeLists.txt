cmake_minimum_required(VERSION 3.20)
project(GtkBittorrentGtkPreview LANGUAGES CXX)

include(CTest)
find_package(PkgConfig REQUIRED)
pkg_check_modules(GTKMM REQUIRED IMPORTED_TARGET gtkmm-4.0>=4.20)
add_subdirectory("../engine" "engine")

add_library(gtkbittorrent_gtk STATIC magnetdialog.cpp window.cpp torrentrow.cpp)
target_compile_features(gtkbittorrent_gtk PUBLIC cxx_std_20)
target_include_directories(gtkbittorrent_gtk PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/..")
target_link_libraries(gtkbittorrent_gtk PUBLIC PkgConfig::GTKMM gtkbittorrent_engine_client)
set_target_properties(gtkbittorrent_gtk PROPERTIES CXX_EXTENSIONS OFF)

add_executable(gtkbittorrent_gtk_preview main.cpp)
target_link_libraries(gtkbittorrent_gtk_preview PRIVATE gtkbittorrent_gtk)
set_target_properties(gtkbittorrent_gtk_preview PROPERTIES OUTPUT_NAME gtkbittorrent-gtk CXX_EXTENSIONS OFF)

if (BUILD_TESTING)
    find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
    find_package(nlohmann_json 3.11 REQUIRED)
    find_program(XVFB_RUN xvfb-run REQUIRED)
    find_program(DBUS_RUN_SESSION dbus-run-session REQUIRED)
    add_executable(gtk_probe "../../test/gtk_probe.cpp")
    target_link_libraries(gtk_probe PRIVATE gtkbittorrent_gtk nlohmann_json::nlohmann_json)
    set_target_properties(gtk_probe PROPERTIES CXX_EXTENSIONS OFF)
    set(gtkTestArgs --probe "$<TARGET_FILE:gtk_probe>")
    if (ENGINE_TEST_BINARY)
        list(APPEND gtkTestArgs --engine "${ENGINE_TEST_BINARY}")
    endif()
    add_test(NAME testgtk
        COMMAND "${DBUS_RUN_SESSION}" -- "${XVFB_RUN}" -a "${Python3_EXECUTABLE}" -B
            "${CMAKE_CURRENT_SOURCE_DIR}/../../test/testgtk.py" ${gtkTestArgs}
    )
    set_tests_properties(testgtk PROPERTIES LABELS "gtk;integration" TIMEOUT 60)
endif()
