/*
 * CV2X-IDS: trace wiring and per-node instrumentation.
 *
 * Opens the receive-side and transmit-side tables, connects the NR sidelink
 * PHY and MAC traces, and gives every station a channel monitor. The tables it
 * writes are the raw material the offline feature pipeline joins.
 */
#ifndef CV2X_IDS_HELPER_H
#define CV2X_IDS_HELPER_H

#include "ns3/node-container.h"
#include "ns3/nstime.h"
#include "ns3/simulator.h"

#include <string>

namespace ns3
{

class Cv2xIdsHelper
{
  public:
    /// Configure the output location and open every table.
    static void EnableTraces(const std::string& outputDir, const std::string& runTag);

    /// Aggregate a SlChannelMonitor onto each node and connect it to that
    /// node's PSCCH receive trace.
    static void InstallChannelMonitors(const NodeContainer& nodes,
                                       uint16_t numSubchannels,
                                       Time slotDuration,
                                       double slotFraction = 1.0);

    /// Connect the NR sidelink PHY and MAC traces to the CSV tables.
    static void ConnectRadioTraces();

    /// Record one station's identity and role. Written once per station.
    static void RecordStation(uint32_t nodeId,
                              uint32_t stationId,
                              const std::string& role,
                              int attackId,
                              const std::string& attackName);

    /// Flush every table on a repeating schedule, so an interrupted run still
    /// leaves usable output.
    static void ScheduleFlush(Time period);

    /// Flush every table.
    static void Close();

    /// Extract the node id from an ns-3 trace context path.
    static uint32_t NodeIdFromContext(const std::string& context);
};

} // namespace ns3

#endif /* CV2X_IDS_HELPER_H */
