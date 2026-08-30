/*
 * CV2X-IDS: per-node sidelink channel monitor.
 *
 * 5G-LENA does not implement the TS 38.215 Channel Busy Ratio, and it exposes
 * no per-sub-channel S-RSSI. This class reconstructs a CBR estimate from the
 * PSCCH receptions the node actually observes. Every received PSCCH signal is
 * counted, corrupt ones included, because the NrSpectrumPhy fires its receive
 * trace for collided transmissions too. The estimate is therefore
 * energy-based in spirit rather than decode-based, but it still misses energy
 * below the PSCCH detection threshold. That limitation is stated in the paper
 * and is the reason the metric is reported as a CBR ESTIMATE.
 *
 * The same object keeps the most recent SL-RSRP per observed transmitter,
 * which is the input to the strongest cross-layer feature: received power
 * against the distance the sender claims to be at.
 */
#ifndef CV2X_SL_CHANNEL_MONITOR_H
#define CV2X_SL_CHANNEL_MONITOR_H

#include "ns3/nstime.h"
#include "ns3/object.h"

#include <deque>
#include <map>

namespace ns3
{

class SlChannelMonitor : public Object
{
  public:
    static TypeId GetTypeId();
    SlChannelMonitor();
    ~SlChannelMonitor() override;

    /**
     * \brief Pool geometry, needed to normalise occupancy into a ratio.
     * \param numSubchannels sub-channels in the resource pool
     * \param slotDuration one slot at the configured numerology
     * \param slotFraction fraction of slots that actually carry sidelink
     *
     * The slot fraction matters more than it looks. Sidelink transmits only in
     * the uplink slots the TDD pattern allows, further masked by the resource
     * pool's time bitmap. Measured on the default configuration only 42 percent
     * of slots carry sidelink at all. Normalising against every slot understates
     * the channel busy ratio by roughly 2.4 times, which in turn stops the DCC
     * gating from ever leaving its relaxed state.
     */
    void SetPoolGeometry(uint16_t numSubchannels, Time slotDuration, double slotFraction = 1.0);

    /// Record one received PSCCH signal.
    void NotifyPscchRx(double timeMs,
                       uint16_t txRnti,
                       uint8_t lengthSubChannel,
                       double slRsrpDbm,
                       bool corrupt);

    /// TS 38.215-style channel busy ratio estimate over the trailing window.
    double GetCbr() const;

    /// Most recent SL-RSRP in dBm observed from a given transmitter RNTI.
    /// Returns false if that transmitter has not been heard inside the window.
    bool GetLastRsrp(uint16_t txRnti, double& rsrpDbm) const;

    /// Distinct transmitters heard in the trailing window. A cheap neighbour
    /// count, used to drive CPM generation.
    uint32_t GetNeighbourCount() const;

  private:
    void Prune() const;

    struct Sample
    {
        double timeMs;
        uint16_t txRnti;
        uint8_t subChannels;
        double rsrpDbm;
    };

    mutable std::deque<Sample> m_window;
    uint16_t m_numSubchannels{1};
    Time m_slotDuration{MilliSeconds(1)};
    double m_slotFraction{1.0}; //!< share of slots usable for sidelink
    Time m_cbrWindow{MilliSeconds(100)}; //!< 100 slots at 15 kHz SCS, per TS 38.215
};

} // namespace ns3

#endif /* CV2X_SL_CHANNEL_MONITOR_H */
