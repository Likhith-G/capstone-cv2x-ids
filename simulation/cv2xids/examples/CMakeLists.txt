build_lib_example(
  NAME cv2x-ids-scenario
  SOURCE_FILES cv2x-ids-scenario.cc
  LIBRARIES_TO_LINK
    ${libcv2xids}
    ${libnr}
    ${liblte}
    ${libinternet}
    ${libmobility}
    ${libapplications}
    ${libpoint-to-point}
    ${libconfig-store}
    ${libantenna}
)
