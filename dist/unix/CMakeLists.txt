if (SYSTEMD)
    if (NOT SYSTEMD_SERVICES_INSTALL_DIR)
        find_package(Systemd)
        if (NOT SYSTEMD_FOUND)
            message(
                FATAL_ERROR
                "Could not locate systemd services install dir."
                " Either pass the -DSYSTEMD_SERVICES_INSTALL_DIR=/path/to/systemd/services option"
                " or install systemd pkg-config"
            )
        endif()
    endif()
    set(EXPAND_BINDIR ${CMAKE_INSTALL_FULL_BINDIR})
    configure_file(systemd/gtkbittorrent-engine@.service.in ${CMAKE_CURRENT_BINARY_DIR}/gtkbittorrent-engine@.service @ONLY)
    install(FILES "${CMAKE_CURRENT_BINARY_DIR}/gtkbittorrent-engine@.service"
        DESTINATION ${SYSTEMD_SERVICES_INSTALL_DIR}
        COMPONENT data
    )
endif()

set(manPageLanguages
    en
    ru
)

foreach(manPageLanguage ${manPageLanguages})
    install(FILES ${PROJECT_SOURCE_DIR}/doc/${manPageLanguage}/$<IF:$<BOOL:${GUI}>,qbittorrent.1,qbittorrent-nox.1>
        # English man pages are installed into ${CMAKE_INSTALL_MANDIR}/man1, while man pages
        # in other languages are installed into ${CMAKE_INSTALL_MANDIR}/${manPageLanguage}/man1.
        DESTINATION ${CMAKE_INSTALL_MANDIR}/$<$<NOT:$<STREQUAL:${manPageLanguage},en>>:${manPageLanguage}/>man1
        COMPONENT doc
        RENAME $<IF:$<BOOL:${GUI}>,gtkbittorrent.1,gtkbittorrent-engine.1>
    )
endforeach()

if (GUI)
    file(READ org.qbittorrent.qBittorrent.desktop desktopEntry)
    string(REPLACE "qBittorrent" "gtkBittorrent" desktopEntry "${desktopEntry}")
    string(REPLACE "qbittorrent" "gtkbittorrent" desktopEntry "${desktopEntry}")
    file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/io.github.gstn_caruso.gtkBittorrent.desktop" "${desktopEntry}")
    install(FILES "${CMAKE_CURRENT_BINARY_DIR}/io.github.gstn_caruso.gtkBittorrent.desktop"
        DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/applications
        COMPONENT data
    )

    install(FILES io.github.gstn_caruso.gtkBittorrent.metainfo.xml
        DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/metainfo
        COMPONENT data
    )

    file(GLOB_RECURSE menuIcons RELATIVE "${CMAKE_CURRENT_SOURCE_DIR}/menuicons" "menuicons/*")
    foreach(icon IN LISTS menuIcons)
        get_filename_component(iconDirectory "${icon}" DIRECTORY)
        get_filename_component(iconName "${icon}" NAME)
        string(REPLACE "qbittorrent" "gtkbittorrent" iconName "${iconName}")
        install(FILES "menuicons/${icon}"
            DESTINATION "${CMAKE_INSTALL_DATAROOTDIR}/icons/hicolor/${iconDirectory}"
            RENAME "${iconName}"
            COMPONENT data
        )
    endforeach()

    foreach(trayIcon IN ITEMS tray tray-dark tray-light)
        install(FILES "${PROJECT_SOURCE_DIR}/src/icons/qbittorrent-${trayIcon}.svg"
            DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/icons/hicolor/scalable/status
            RENAME "gtkbittorrent-${trayIcon}.svg"
            COMPONENT data
        )
    endforeach()
else()
    install(FILES io.github.gstn_caruso.gtkBittorrent.Engine.metainfo.xml
        DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/metainfo
        COMPONENT data
    )
endif()
