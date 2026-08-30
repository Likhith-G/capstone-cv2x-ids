#include "sl-channel-monitor.h"

#include "ns3/log.h"
#include "ns3/simulator.h"

#include <set>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("SlChannelMonitor");
NS_OBJECT_ENSURE_REGISTERED(SlChannelMonitor);

TypeId
SlChannelMonitor::GetTypeId()
{
    static TypeId tid = TypeId("ns3::SlChannelMonitor")
                            .SetParent<Object>()
                            .SetGroupName("Cv2xIds")
                            .AddConstructor<SlChannelMonitor>()
                            .AddAttribute("CbrWindow",
                                          "Trailing window over which the CBR estimate is taken",
                                          TimeValue(MilliSeconds(100)),
                                          MakeTimeAccessor(&SlChannelMonitor::m_cbrWindow),
                                          MakeTimeChecker());
    return tid;
}

SlChannelMonitor::SlChannelMonitor()
{
}

SlChannelMonitor::~SlChannelMonitor()
{
}

void
SlChannelMonitor::SetPoolGeometry(uint16_t numSubchannels, Time slotDuration, double slotFraction)
{
    m_numSubchannels = numSubchannels == 0 ? 1 : numSubchannels;
    m_slotDuration = slotDuration;
    m_slotFraction = (slotFraction <= 0.0 || slotFraction > 1.0) ? 1.0 : slotFraction;
}

void
SlChannelMonitor::NotifyPscchRx(double timeMs,
                                uint16_t txRnti,
                                uint8_t lengthSubChannel,
                                double slRsrpDbm,
                                bool corrupt)
{
    // Corrupt receptions are kept. They still occupied the channel, and
    // excluding them would bias the CBR estimate downwards exactly when the
    // channel is most congested, which is when the metric matters.
    (void)corrupt;
    m_window.push_back(
        Sample{timeMs, txRnti, lengthSubChannel == 0 ? uint8_t(1) : lengthSubChannel, slRsrpDbm});
    Prune();
}

void
SlChannelMonitor::Prune() const
{
    double cutoff = Simulator::Now().GetSeconds() * 1000.0 - m_cbrWindow.GetMilliSeconds();
    while (!m_window.empty() && m_window.front().timeMs < cutoff)
    {
        m_window.pop_front();
    }
}

double
SlChannelMonitor::GetCbr() const
{
    Prune();
    double slotsInWindow = m_cbrWindow.GetSeconds() / m_slotDuration.GetSeconds();
    if (slotsInWindow <= 0.0)
    {
        return 0.0;
    }
    double occupied = 0.0;
    for (const auto& s : m_window)
    {
        occupied += s.subChannels;
    }
    // Only the sidelink-capable slots are capacity. See SetPoolGeometry.
    double capacity = slotsInWindow * m_slotFraction * static_cast<double>(m_numSubchannels);
    double cbr = occupied / capacity;
    return cbr > 1.0 ? 1.0 : cbr;
}

bool
SlChannelMonitor::GetLastRsrp(uint16_t txRnti, double& rsrpDbm) const
{
    Prune();
    for (auto it = m_window.rbegin(); it != m_window.rend(); ++it)
    {
        if (it->txRnti == txRnti)
        {
            rsrpDbm = it->rsrpDbm;
            return true;
        }
    }
    return false;
}

uint32_t
SlChannelMonitor::GetNeighbourCount() const
{
    Prune();
    std::set<uint16_t> seen;
    for (const auto& s : m_window)
    {
        seen.insert(s.txRnti);
    }
    return static_cast<uint32_t>(seen.size());
}

} // namespace ns3
