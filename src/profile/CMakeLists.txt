cmake_minimum_required(VERSION 3.16)

if (CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    project(GtkBittorrentProfileTools LANGUAGES CXX)
    include(CTest)
    include(GNUInstallDirs)
    set(profileStandalone ON)
endif()

add_library(gtkbittorrent_profile STATIC profileimporter.cpp)
target_compile_features(gtkbittorrent_profile PUBLIC cxx_std_20)
target_include_directories(gtkbittorrent_profile PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/..")
set_target_properties(gtkbittorrent_profile PROPERTIES AUTOMOC OFF AUTORCC OFF CXX_EXTENSIONS OFF)

add_executable(gtkbittorrent_import main.cpp)
target_link_libraries(gtkbittorrent_import PRIVATE gtkbittorrent_profile)
set_target_properties(gtkbittorrent_import PROPERTIES
    OUTPUT_NAME gtkbittorrent-import
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
    AUTOMOC OFF
    AUTORCC OFF
    CXX_EXTENSIONS OFF
)
if (MINGW)
    target_link_options(gtkbittorrent_import PRIVATE -municode)
endif()
install(TARGETS gtkbittorrent_import RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR} COMPONENT runtime)

if (TESTING OR (profileStandalone AND BUILD_TESTING))
    enable_testing()
    find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
    add_test(NAME testprofileimport
        COMMAND "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/../../test/testprofileimport.py"
            --importer "$<TARGET_FILE:gtkbittorrent_import>"
    )
    set_tests_properties(testprofileimport PROPERTIES LABELS "integration;profile" TIMEOUT 30)
    if (profileStandalone)
        add_custom_target(check COMMAND ${CMAKE_CTEST_COMMAND} --output-on-failure DEPENDS gtkbittorrent_import)
    endif()
endif()
