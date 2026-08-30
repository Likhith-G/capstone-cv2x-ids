#include "cv2x-ids-helper.h"

#include "ns3/cv2x-trace-store.h"
#include "ns3/config.h"
#include "ns3/log.h"
#include "ns3/node-list.h"
#include "ns3/nr-sl-phy-mac-common.h"
#include "ns3/simulator.h"
#include "ns3/sl-channel-monitor.h"

#include <sstream>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("Cv2xIdsHelper");

namespace
{

void
PscchRxSink(std::string context, const SlRxCtrlPacketTraceParams p)
{
    uint32_t nodeId = Cv2xIdsHelper::NodeIdFromContext(context);

    // Feed the node's own channel monitor. This is the only in-simulation
    // consumer; everything else is written out for offline processing.
    Ptr<Node> node = NodeList::GetNode(nodeId);
    Ptr<SlChannelMonitor> mon = node ? node->GetObject<SlChannelMonitor>() : nullptr;
    if (mon)
    {
        mon->NotifyPscchRx(p.m_timeMs, p.m_txRnti, p.m_lengthSubChannel, p.m_slRsrp, p.m_corrupt);
    }

    std::ostringstream row;
    row << p.m_timeMs << ',' << nodeId << ',' << p.m_rnti << ',' << p.m_txRnti << ',' << p.m_dstL2Id
        << ',' << p.m_slRsrp << ',' << p.m_sinr << ',' << p.m_sinrMin << ',' << p.m_tbler << ','
        << (p.m_corrupt ? 1 : 0) << ',' << p.m_rbStart << ',' << p.m_rbEnd << ','
        << +p.m_priority << ',' << p.m_slResourceReservePeriod << ','
        << +p.m_indexStartSubChannel << ',' << +p.m_lengthSubChannel << ','
        << +p.m_maxNumPerReserve << ',' << p.m_frameNum << ',' << +p.m_subframeNum << ','
        << p.m_slotNum;
    Cv2xTraceStore::Get().Write("rx_pscch", row.str());
}

void
PsschRxSink(std::string context, const SlRxDataPacketTraceParams p)
{
    uint32_t nodeId = Cv2xIdsHelper::NodeIdFromContext(context);
    std::ostringstream row;
    row << p.m_timeMs << ',' << nodeId << ',' << p.m_rnti << ',' << p.m_txRnti << ',' << p.m_srcL2Id
        << ',' << p.m_dstL2Id << ',' << p.m_sinr << ',' << p.m_sinrMin << ',' << p.m_tbler << ','
        << (p.m_corrupt ? 1 : 0) << ',' << (p.m_sci2Corrupted ? 1 : 0) << ',' << p.m_tblerSci2
        << ',' << +p.m_mcs << ',' << p.m_tbSize << ',' << p.m_rbStart << ',' << p.m_rbEnd << ','
        << +p.m_ndi << ',' << +p.m_rv << ',' << p.m_frameNum << ',' << +p.m_subframeNum << ','
        << p.m_slotNum;
    Cv2xTraceStore::Get().Write("rx_pssch", row.str());
}

void
PscchTxSink(std::string context, const SlPscchUeMacStatParameters p)
{
    uint32_t nodeId = Cv2xIdsHelper::NodeIdFromContext(context);
    std::ostringstream row;
    row << p.timeMs << ',' << nodeId << ',' << p.rnti << ',' << p.imsi << ',' << p.rbStart << ','
        << p.rbLength << ',' << +p.priority << ',' << +p.mcs << ',' << p.tbSize << ','
        << p.slResourceReservePeriod << ',' << p.totalSubChannels << ',' << p.slPsschSubChStart
        << ',' << p.slPsschSubChLength << ',' << +p.slMaxNumPerReserve << ',' << +p.gapReTx1 << ','
        << +p.gapReTx2 << ',' << p.frameNum << ',' << p.subframeNum << ',' << p.slotNum;
    Cv2xTraceStore::Get().Write("tx_pscch", row.str());
}

void
PsschTxSink(std::string context, const SlPsschUeMacStatParameters p)
{
    uint32_t nodeId = Cv2xIdsHelper::NodeIdFromContext(context);
    std::ostringstream row;
    row << p.timeMs << ',' << nodeId << ',' << p.rnti << ',' << p.srcL2Id << ',' << p.dstL2Id << ','
        << p.rbStart << ',' << p.rbLength << ',' << p.subChannelSize << ',' << +p.harqId << ','
        << +p.ndi << ',' << +p.rv << ',' << +p.castType << ',' << +p.resoReselCounter << ','
        << p.cReselCounter << ',' << p.frameNum << ',' << p.subframeNum << ',' << p.slotNum;
    Cv2xTraceStore::Get().Write("tx_pssch", row.str());
}

} // namespace

uint32_t
Cv2xIdsHelper::NodeIdFromContext(const std::string& context)
{
    // Contexts look like "/NodeList/7/DeviceList/0/$ns3::NrUeNetDevice/..."
    const std::string marker = "/NodeList/";
    size_t start = context.find(marker);
    if (start == std::string::npos)
    {
        return std::numeric_limits<uint32_t>::max();
    }
    start += marker.size();
    size_t end = context.find('/', start);
    return static_cast<uint32_t>(std::stoul(context.substr(start, end - start)));
}

void
Cv2xIdsHelper::EnableTraces(const std::string& outputDir, const std::string& runTag)
{
    auto& store = Cv2xTraceStore::Get();
    store.Configure(outputDir, runTag);

    store.Open("rx_pscch",
               "timeMs,rxNodeId,rxRnti,txRnti,dstL2Id,slRsrpDbm,sinr,sinrMin,tbler,corrupt,"
               "rbStart,rbEnd,priority,rsvpMs,subChStart,subChLen,maxNumPerReserve,"
               "frame,subframe,slot");
    store.Open("rx_pssch",
               "timeMs,rxNodeId,rxRnti,txRnti,srcL2Id,dstL2Id,sinr,sinrMin,tbler,corrupt,"
               "sci2Corrupt,tblerSci2,mcs,tbSize,rbStart,rbEnd,ndi,rv,frame,subframe,slot");
    store.Open("tx_pscch",
               "timeMs,txNodeId,rnti,imsi,rbStart,rbLength,priority,mcs,tbSize,rsvpMs,"
               "totalSubChannels,psschSubChStart,psschSubChLen,maxNumPerReserve,"
               "gapReTx1,gapReTx2,frame,subframe,slot");
    store.Open("tx_pssch",
               "timeMs,txNodeId,rnti,srcL2Id,dstL2Id,rbStart,rbLength,subChannelSize,harqId,"
               "ndi,rv,castType,resoReselCounter,cReselCounter,frame,subframe,slot");
    store.Open("stations", "nodeId,stationId,role,attackId,attackName");
}

void
Cv2xIdsHelper::InstallChannelMonitors(const NodeContainer& nodes,
                                      uint16_t numSubchannels,
                                      Time slotDuration,
                                      double slotFraction)
{
    for (uint32_t i = 0; i < nodes.GetN(); ++i)
    {
        Ptr<SlChannelMonitor> mon = CreateObject<SlChannelMonitor>();
        mon->SetPoolGeometry(numSubchannels, slotDuration, slotFraction);
        nodes.Get(i)->AggregateObject(mon);
    }
}

void
Cv2xIdsHelper::ConnectRadioTraces()
{
    Config::Connect("/NodeList/*/DeviceList/*/$ns3::NrUeNetDevice/ComponentCarrierMapUe/*/"
                    "NrUePhy/SpectrumPhy/RxPscchTraceUe",
                    MakeCallback(&PscchRxSink));
    Config::Connect("/NodeList/*/DeviceList/*/$ns3::NrUeNetDevice/ComponentCarrierMapUe/*/"
                    "NrUePhy/SpectrumPhy/RxPsschTraceUe",
                    MakeCallback(&PsschRxSink));
    Config::Connect("/NodeList/*/DeviceList/*/$ns3::NrUeNetDevice/ComponentCarrierMapUe/*/"
                    "NrUeMac/SlPscchScheduling",
                    MakeCallback(&PscchTxSink));
    Config::Connect("/NodeList/*/DeviceList/*/$ns3::NrUeNetDevice/ComponentCarrierMapUe/*/"
                    "NrUeMac/SlPsschScheduling",
                    MakeCallback(&PsschTxSink));
}

void
Cv2xIdsHelper::RecordStation(uint32_t nodeId,
                             uint32_t stationId,
                             const std::string& role,
                             int attackId,
                             const std::string& attackName)
{
    std::ostringstream row;
    row << nodeId << ',' << stationId << ',' << role << ',' << attackId << ',' << attackName;
    Cv2xTraceStore::Get().Write("stations", row.str());
}

void
Cv2xIdsHelper::ScheduleFlush(Time period)
{
    Cv2xTraceStore::Get().FlushAll();
    Simulator::Schedule(period, &Cv2xIdsHelper::ScheduleFlush, period);
}

void
Cv2xIdsHelper::Close()
{
    Cv2xTraceStore::Get().CloseAll();
}

} // namespace ns3
