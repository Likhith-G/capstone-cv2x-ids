# CV2X-IDS: cross-layer misbehaviour dataset generation for NR sidelink.
# SPDX-License-Identifier: GPL-2.0-only

set(source_files
    model/its-message-header.cc
    model/cv2x-trace-store.cc
    model/sl-channel-monitor.cc
    model/highway-traffic-model.cc
    model/its-station-app.cc
    helper/cv2x-ids-helper.cc
)

set(header_files
    model/its-message-header.h
    model/cv2x-trace-store.h
    model/sl-channel-monitor.h
    model/highway-traffic-model.h
    model/its-station-app.h
    helper/cv2x-ids-helper.h
)

build_lib(
  LIBNAME cv2xids
  SOURCE_FILES ${source_files}
  HEADER_FILES ${header_files}
  LIBRARIES_TO_LINK
    ${libnr}
    ${libcore}
    ${libnetwork}
    ${libmobility}
    ${libinternet}
    ${libapplications}
)
