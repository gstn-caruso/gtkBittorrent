find_package(Qt6 REQUIRED COMPONENTS Test)

enable_testing(true)
add_custom_target(check COMMAND ${CMAKE_CTEST_COMMAND} --output-on-failure
    WORKING_DIRECTORY "${CMAKE_BINARY_DIR}"
)
add_dependencies(check gtkbittorrent_import)

include_directories("../src")

set(testFiles
    testalgorithm.cpp
    testbittorrentpeeraddress.cpp
    testbittorrenttorrentdescriptor.cpp
    testbittorrenttrackerentry.cpp
    testconceptsexplicitlyconvertibleto.cpp
    testconceptsstringable.cpp
    testglobal.cpp
    testorderedset.cpp
    testpath.cpp
    testutilsbytearray.cpp
    testutilscompare.cpp
    testutilsdatetime.cpp
    testutilsdict.cpp
    testutilsfs.cpp
    testutilsgzip.cpp
    testutilshashvalue.cpp
    testutilsio.cpp
    testutilsmisc.cpp
    testutilsnet.cpp
    testutilsnumber.cpp
    testutilsstring.cpp
    testutilsversion.cpp
)

foreach(testFile ${testFiles})
    get_filename_component(testFilename "${testFile}" NAME_WLE)

    add_executable("${testFilename}" "${testFile}")
    target_link_libraries("${testFilename}" PRIVATE Qt::Test qbt_base)
    add_test(NAME "${testFilename}" COMMAND "${testFilename}")

    add_dependencies(check "${testFilename}")
endforeach()

if (WEBUI AND NOT GUI)
    find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
    add_test(NAME testsession
        COMMAND "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/testsession.py"
            --binary "$<TARGET_FILE:qbt_app>"
            --importer "$<TARGET_FILE:gtkbittorrent_import>"
    )
    set_tests_properties(testsession PROPERTIES
        LABELS "integration;session"
        TIMEOUT 180
    )
    add_dependencies(check qbt_app)
endif()

if (NOT WIN32 OR NOT GUI)
    find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
    add_test(NAME testidentity
        COMMAND "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/testidentity.py"
            --binary "$<TARGET_FILE:qbt_app>"
    )
    set_tests_properties(testidentity PROPERTIES LABELS "integration;identity" TIMEOUT 30)
    add_dependencies(check qbt_app)
endif()
