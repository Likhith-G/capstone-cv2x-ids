/*
 * simulation.cc -- Capstone: Cybersecurity for Connected Cars
 * Unified 5G NR + V2X IDS dataset generation script (scaled)
 *
 * Produces per-packet CSV log with true positions from NS-3 MobilityModel.
 *
 * Usage:
 *   ./ns3 run "scratch/simulation --scenario=S00"
 *   ./ns3 run "scratch/simulation --scenario=S01 --attackType=UDPFlood"
 *   ./ns3 run "scratch/simulation --scenario=S06 --attackType=PositionSpoof"
 *
 * Scenarios:
 *   S00  Benign (baseline)
 *   S01  UDPFlood          S02  ICMPFlood
 *   S03  SYNFlood          S04  HTTPFlood       S05  SlowDoS
 *   S06  PositionSpoof     S07  RandomPosition  S08  Replay
 *   S09  FalseDataInjection S10  Sybil          S11  VehicularDoS
 *
 * Scale: 40 UEs, 4 gNBs, 600s sim, 5 attackers per scenario
 */

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/applications-module.h"
#include "ns3/flow-monitor-module.h"
#include "ns3/mobility-module.h"
#include "ns3/nr-module.h"

#include <fstream>
#include <sstream>
#include <deque>
#include <cmath>
#include <iomanip>

using namespace ns3;
NS_LOG_COMPONENT_DEFINE("V2xIdsSimulation");

// ---------------------------------------------------------------------------
// Global packet log (written by all application instances, safe in
// single-threaded NS-3)
// ---------------------------------------------------------------------------
static std::ofstream g_packetLog;

// ---------------------------------------------------------------------------
// BSM payload -- plain-old-data struct serialised into every UDP packet.
// 32 bytes.
// ---------------------------------------------------------------------------
struct BsmPayload
{
    uint32_t vehicleId;
    uint32_t seqNum;
    double   claimedX;
    double   claimedY;
    float    claimedSpeed;
    float    claimedHeading;
};

// ---------------------------------------------------------------------------
// Cached BSM entry (used by Replay attack to store past honest positions)
// ---------------------------------------------------------------------------
struct CachedBsm
{
    double   time;
    double   claimedX;
    double   claimedY;
    float    claimedSpeed;
    float    claimedHeading;
    uint32_t seqNum;
};

// ===========================================================================
// BsmApplication -- custom NS-3 Application for BSM transmission + logging.
// Handles all vehicular attack types internally.
// ===========================================================================
class BsmApplication : public Application
{
  public:
    static TypeId GetTypeId()
    {
        static TypeId tid =
            TypeId("ns3::BsmApplication")
                .SetParent<Application>()
                .SetGroupName("Applications")
                .AddConstructor<BsmApplication>();
        return tid;
    }

    BsmApplication()
        : m_socket(nullptr),
          m_port(0),
          m_interval(MilliSeconds(100)),
          m_vehicleId(0),
          m_pktSize(200),
          m_attackType("Benign"),
          m_label(0),
          m_seqNum(0),
          m_replayDelay(5.0),
          m_replayWarmup(10.0),
          m_nSybilIds(5),
          m_sybilBaseId(100),
          m_sybilRadius(15.0),
          m_posOffsetX(500.0),
          m_posOffsetY(0.0)
    {
        m_rng = CreateObject<UniformRandomVariable>();
    }

    void Setup(Ipv4Address remoteAddr, uint16_t port, Time interval,
               uint32_t vehicleId, std::string attackType, uint32_t pktSize)
    {
        m_remoteAddr = remoteAddr;
        m_port       = port;
        m_interval   = interval;
        m_vehicleId  = vehicleId;
        m_attackType = attackType;
        m_pktSize    = pktSize;
        m_label      = (attackType == "Benign") ? 0 : 1;
    }

  private:
    void StartApplication() override
    {
        m_socket = Socket::CreateSocket(GetNode(),
                                        UdpSocketFactory::GetTypeId());
        m_socket->Connect(InetSocketAddress(m_remoteAddr, m_port));
        SendBsm();
    }

    void StopApplication() override
    {
        m_sendEvent.Cancel();
        if (m_socket)
        {
            m_socket->Close();
            m_socket = nullptr;
        }
    }

    void SendBsm()
    {
        double now = Simulator::Now().GetSeconds();

        // -- True kinematics from NS-3 MobilityModel (ground truth) --------
        Ptr<MobilityModel> mob = GetNode()->GetObject<MobilityModel>();
        Vector truePos = mob->GetPosition();
        Vector trueVel = mob->GetVelocity();
        double trueSpeed =
            std::sqrt(trueVel.x * trueVel.x + trueVel.y * trueVel.y);
        double trueHeading =
            std::atan2(trueVel.y, trueVel.x) * 180.0 / M_PI;

        // -- Default: honest reporting (benign) ----------------------------
        double   claimedX       = truePos.x;
        double   claimedY       = truePos.y;
        float    claimedSpeed   = static_cast<float>(trueSpeed);
        float    claimedHeading = static_cast<float>(trueHeading);
        uint32_t vehicleId      = m_vehicleId;
        uint32_t seqNum         = m_seqNum;
        uint8_t  label          = m_label;

        // -- Attack-specific BSM manipulation ------------------------------
        if (m_attackType == "PositionSpoof")
        {
            claimedX = truePos.x + m_posOffsetX;
            claimedY = truePos.y + m_posOffsetY;
        }
        else if (m_attackType == "RandomPosition")
        {
            claimedX = m_rng->GetValue(-500.0, 2000.0);
            claimedY = m_rng->GetValue(-200.0, 200.0);
        }
        else if (m_attackType == "Replay")
        {
            // Always cache the HONEST position first (before overriding)
            CachedBsm entry;
            entry.time          = now;
            entry.claimedX      = truePos.x;
            entry.claimedY      = truePos.y;
            entry.claimedSpeed  = static_cast<float>(trueSpeed);
            entry.claimedHeading = static_cast<float>(trueHeading);
            entry.seqNum        = m_seqNum;
            m_bsmCache.push_back(entry);
            if (m_bsmCache.size() > 200)
            {
                m_bsmCache.pop_front();
            }

            // After warmup, replay a BSM from m_replayDelay seconds ago
            if (now > m_replayWarmup)
            {
                double targetTime = now - m_replayDelay;
                for (auto it = m_bsmCache.rbegin();
                     it != m_bsmCache.rend(); ++it)
                {
                    if (it->time <= targetTime)
                    {
                        claimedX       = it->claimedX;
                        claimedY       = it->claimedY;
                        claimedSpeed   = it->claimedSpeed;
                        claimedHeading = it->claimedHeading;
                        seqNum         = it->seqNum;
                        break;
                    }
                }
            }
        }
        else if (m_attackType == "FalseDataInjection")
        {
            // Falsified speed: proportional to true speed (2.5x - 4.0x)
            claimedSpeed = static_cast<float>(
                trueSpeed * m_rng->GetValue(2.5, 4.0));
        }
        else if (m_attackType == "Sybil")
        {
            // Cycle through N fake vehicle IDs from one physical node
            uint32_t sybilIndex = m_seqNum % m_nSybilIds;
            vehicleId = m_sybilBaseId + sybilIndex;

            // Each fake identity claims a position arranged in a circle
            // around the true position (to simulate separate vehicles)
            double theta = 2.0 * M_PI * sybilIndex / m_nSybilIds;
            claimedX = truePos.x + m_sybilRadius * std::cos(theta);
            claimedY = truePos.y + m_sybilRadius * std::sin(theta);
            claimedSpeed = static_cast<float>(
                trueSpeed +
                2.0 * (static_cast<double>(sybilIndex) -
                        static_cast<double>(m_nSybilIds) / 2.0));
        }
        // VehicularDoS: normal BSM content, m_interval already set to 1ms

        // -- Build and send packet -----------------------------------------
        BsmPayload payload;
        payload.vehicleId     = vehicleId;
        payload.seqNum        = seqNum;
        payload.claimedX      = claimedX;
        payload.claimedY      = claimedY;
        payload.claimedSpeed  = claimedSpeed;
        payload.claimedHeading = claimedHeading;

        Ptr<Packet> pkt = Create<Packet>(
            reinterpret_cast<const uint8_t*>(&payload), sizeof(BsmPayload));

        // Pad to desired total packet size
        if (m_pktSize > sizeof(BsmPayload))
        {
            Ptr<Packet> padding =
                Create<Packet>(m_pktSize - sizeof(BsmPayload));
            pkt->AddAtEnd(padding);
        }

        m_socket->Send(pkt);

        // -- Write to per-packet CSV log -----------------------------------
        g_packetLog << std::fixed << std::setprecision(6)
                    << now << ","
                    << GetNode()->GetId() << ","
                    << vehicleId << ","
                    << seqNum << ","
                    << std::setprecision(4)
                    << claimedX << ","
                    << claimedY << ","
                    << claimedSpeed << ","
                    << claimedHeading << ","
                    << truePos.x << ","
                    << truePos.y << ","
                    << trueSpeed << ","
                    << pkt->GetSize() << ","
                    << "bsm,"
                    << static_cast<int>(label) << "\n";

        m_seqNum++;
        m_sendEvent =
            Simulator::Schedule(m_interval, &BsmApplication::SendBsm, this);
    }

    // -- Members -----------------------------------------------------------
    Ptr<Socket>      m_socket;
    Ipv4Address      m_remoteAddr;
    uint16_t         m_port;
    Time             m_interval;
    uint32_t         m_vehicleId;
    uint32_t         m_pktSize;
    std::string      m_attackType;
    uint8_t          m_label;
    uint32_t         m_seqNum;
    EventId          m_sendEvent;
    Ptr<UniformRandomVariable> m_rng;

    // Replay
    double                   m_replayDelay;
    double                   m_replayWarmup;
    std::deque<CachedBsm>   m_bsmCache;

    // Sybil
    uint32_t m_nSybilIds;
    uint32_t m_sybilBaseId;
    double   m_sybilRadius;

    // PositionSpoof
    double m_posOffsetX;
    double m_posOffsetY;
};

NS_OBJECT_ENSURE_REGISTERED(BsmApplication);

// ===========================================================================
// FloodApplication -- network attack traffic generator.
// Supports UDP and TCP, with optional on/off cycling.
// Logs every sent packet to g_packetLog for proper feature extraction.
// ===========================================================================
class FloodApplication : public Application
{
  public:
    static TypeId GetTypeId()
    {
        static TypeId tid =
            TypeId("ns3::FloodApplication")
                .SetParent<Application>()
                .SetGroupName("Applications")
                .AddConstructor<FloodApplication>();
        return tid;
    }

    FloodApplication()
        : m_socket(nullptr),
          m_port(0),
          m_interval(MicroSeconds(100)),
          m_pktSize(1024),
          m_seqNum(0),
          m_isTcp(false),
          m_connected(false),
          m_onDuration(Seconds(0)),
          m_offDuration(Seconds(0)),
          m_startTime(0.0) {}

    void Setup(Ipv4Address remoteAddr, uint16_t port,
               Time interval, uint32_t pktSize, bool isTcp = false,
               Time onDuration = Seconds(0), Time offDuration = Seconds(0))
    {
        m_remoteAddr  = remoteAddr;
        m_port        = port;
        m_interval    = interval;
        m_pktSize     = pktSize;
        m_isTcp       = isTcp;
        m_onDuration  = onDuration;
        m_offDuration = offDuration;
    }

  private:
    void StartApplication() override
    {
        m_startTime = Simulator::Now().GetSeconds();
        if (m_isTcp)
        {
            m_socket = Socket::CreateSocket(
                GetNode(), TcpSocketFactory::GetTypeId());
            m_socket->SetConnectCallback(
                MakeCallback(&FloodApplication::OnConnectOk, this),
                MakeCallback(&FloodApplication::OnConnectFail, this));
            m_socket->Bind();
            m_socket->Connect(
                InetSocketAddress(m_remoteAddr, m_port));
        }
        else
        {
            m_socket = Socket::CreateSocket(
                GetNode(), UdpSocketFactory::GetTypeId());
            m_socket->Connect(
                InetSocketAddress(m_remoteAddr, m_port));
            m_connected = true;
            SendPacket();
        }
    }

    void OnConnectOk(Ptr<Socket> socket)
    {
        m_connected = true;
        NS_LOG_UNCOND("FloodApplication TCP connected on node "
                      << GetNode()->GetId());
        SendPacket();
    }

    void OnConnectFail(Ptr<Socket> socket)
    {
        NS_LOG_UNCOND("FloodApplication TCP connect FAILED on node "
                      << GetNode()->GetId() << ", retrying in 1s...");
        Simulator::Schedule(Seconds(1.0),
                            &FloodApplication::RetryConnect, this);
    }

    void RetryConnect()
    {
        if (m_socket)
        {
            m_socket->Close();
        }
        m_socket = Socket::CreateSocket(
            GetNode(), TcpSocketFactory::GetTypeId());
        m_socket->SetConnectCallback(
            MakeCallback(&FloodApplication::OnConnectOk, this),
            MakeCallback(&FloodApplication::OnConnectFail, this));
        m_socket->Bind();
        m_socket->Connect(
            InetSocketAddress(m_remoteAddr, m_port));
    }

    void StopApplication() override
    {
        m_sendEvent.Cancel();
        if (m_socket)
        {
            m_socket->Close();
            m_socket = nullptr;
        }
        m_connected = false;
    }

    void SendPacket()
    {
        if (!m_connected) return;

        // On/off cycling: skip sends during "off" phase
        if (m_offDuration > Seconds(0) && m_onDuration > Seconds(0))
        {
            double elapsed =
                Simulator::Now().GetSeconds() - m_startTime;
            double cycleLen =
                (m_onDuration + m_offDuration).GetSeconds();
            double phase = std::fmod(elapsed, cycleLen);
            if (phase >= m_onDuration.GetSeconds())
            {
                // In "off" phase, schedule retry at start of next "on"
                double waitSec = cycleLen - phase;
                m_sendEvent = Simulator::Schedule(
                    Seconds(waitSec),
                    &FloodApplication::SendPacket, this);
                return;
            }
        }

        Ptr<Packet> pkt = Create<Packet>(m_pktSize);
        int sent = m_socket->Send(pkt);

        if (sent > 0)
        {
            Ptr<MobilityModel> mob =
                GetNode()->GetObject<MobilityModel>();
            Vector truePos = mob->GetPosition();
            Vector trueVel = mob->GetVelocity();
            double trueSpeed = std::sqrt(
                trueVel.x * trueVel.x + trueVel.y * trueVel.y);

            g_packetLog << std::fixed << std::setprecision(6)
                << Simulator::Now().GetSeconds() << ","
                << GetNode()->GetId() << ","
                << 0 << ","       // vehicle_id N/A
                << m_seqNum << ","
                << std::setprecision(4)
                << 0.0 << "," << 0.0 << ","   // claimed pos N/A
                << 0.0 << "," << 0.0 << ","   // claimed speed/heading N/A
                << truePos.x << ","
                << truePos.y << ","
                << trueSpeed << ","
                << sent << ","
                << "flood,"
                << 1 << "\n";
        }

        m_seqNum++;
        m_sendEvent = Simulator::Schedule(
            m_interval, &FloodApplication::SendPacket, this);
    }

    Ptr<Socket>  m_socket;
    Ipv4Address  m_remoteAddr;
    uint16_t     m_port;
    Time         m_interval;
    uint32_t     m_pktSize;
    uint32_t     m_seqNum;
    EventId      m_sendEvent;
    bool         m_isTcp;
    bool         m_connected;
    Time         m_onDuration;
    Time         m_offDuration;
    double       m_startTime;
};

NS_OBJECT_ENSURE_REGISTERED(FloodApplication);

// ===========================================================================
// main
// ===========================================================================
int
main(int argc, char* argv[])
{
    // -- Command-line parameters -------------------------------------------
    uint16_t    numUes       = 40;
    double      simTime      = 600.0;
    uint32_t    seed         = 42;
    uint32_t    numAttackers = 5;
    std::string scenario     = "S00";
    std::string attackType   = "Benign";
    std::string outputDir    = "v3_output";

    CommandLine cmd(__FILE__);
    cmd.AddValue("numUes",       "Number of UEs (vehicles)",        numUes);
    cmd.AddValue("simTime",      "Simulation duration in seconds",  simTime);
    cmd.AddValue("seed",         "RNG seed",                        seed);
    cmd.AddValue("numAttackers", "Number of attacker UEs",          numAttackers);
    cmd.AddValue("scenario",     "Scenario ID (S00-S11)",           scenario);
    cmd.AddValue("attackType",   "Attack type string",              attackType);
    cmd.AddValue("outputDir",    "Output directory",                outputDir);
    cmd.Parse(argc, argv);

    RngSeedManager::SetSeed(seed);
    RngSeedManager::SetRun(1);

    // -- Classify attack category ------------------------------------------
    bool isNetworkAttack =
        (attackType == "UDPFlood"   || attackType == "ICMPFlood" ||
         attackType == "SYNFlood"   || attackType == "HTTPFlood" ||
         attackType == "SlowDoS");
    bool isVehicularAttack =
        (attackType == "PositionSpoof"  || attackType == "RandomPosition" ||
         attackType == "Replay"         || attackType == "FalseDataInjection" ||
         attackType == "Sybil"          || attackType == "VehicularDoS");
    bool hasAttacker = isNetworkAttack || isVehicularAttack;

    // -- Open per-packet CSV log -------------------------------------------
    std::string logFile = outputDir + "/packets_" + scenario + ".csv";
    g_packetLog.open(logFile, std::ios::out);
    if (!g_packetLog.is_open())
    {
        std::cerr << "ERROR: Cannot open " << logFile
                  << " -- does the output directory exist?" << std::endl;
        return 1;
    }
    g_packetLog << "tx_time,node_id,vehicle_id,seq_num,"
                << "claimed_x,claimed_y,claimed_speed,claimed_heading,"
                << "true_x,true_y,true_speed,"
                << "pkt_size,pkt_type,label\n";

    // ======================================================================
    // TOPOLOGY (identical across ALL scenarios)
    // ======================================================================

    // -- Nodes -------------------------------------------------------------
    NodeContainer ueNodes;
    ueNodes.Create(numUes);

    NodeContainer gnbNodes;
    gnbNodes.Create(4); // four gNBs along highway corridor

    NodeContainer remoteHostContainer;
    remoteHostContainer.Create(1);
    Ptr<Node> remoteHost = remoteHostContainer.Get(0);

    // -- NR helper + EPC ---------------------------------------------------
    Ptr<NrHelper> nrHelper = CreateObject<NrHelper>();
    Ptr<NrPointToPointEpcHelper> epcHelper =
        CreateObject<NrPointToPointEpcHelper>();
    nrHelper->SetEpcHelper(epcHelper);

    // -- Internet stack on remote host only --------------------------------
    InternetStackHelper internet;
    internet.Install(remoteHostContainer);

    // -- Backhaul: PGW <-> Remote Host (MEC server) -----------------------
    Ptr<Node> pgw = epcHelper->GetPgwNode();
    PointToPointHelper p2ph;
    p2ph.SetDeviceAttribute("DataRate",
                            DataRateValue(DataRate("10Gb/s")));
    p2ph.SetChannelAttribute("Delay", TimeValue(MilliSeconds(1)));
    NetDeviceContainer internetDevices = p2ph.Install(pgw, remoteHost);

    Ipv4AddressHelper ipv4h;
    ipv4h.SetBase("1.0.0.0", "255.0.0.0");
    Ipv4InterfaceContainer internetIpIfaces = ipv4h.Assign(internetDevices);
    Ipv4Address remoteHostAddr = internetIpIfaces.GetAddress(1);

    Ipv4StaticRoutingHelper ipv4RoutingHelper;
    Ptr<Ipv4StaticRouting> remoteHostStaticRouting =
        ipv4RoutingHelper.GetStaticRouting(
            remoteHost->GetObject<Ipv4>());
    remoteHostStaticRouting->AddNetworkRouteTo(
        Ipv4Address("7.0.0.0"), Ipv4Mask("255.0.0.0"), 1);

    // -- NR band config (3.5 GHz, 20 MHz, UMi Street Canyon) -------------
    BandwidthPartInfoPtrVector allBwps;
    CcBwpCreator ccBwpCreator;
    const uint8_t numCcPerBand = 1;
    CcBwpCreator::SimpleOperationBandConf bandConf(
        3.5e9, 20e6, numCcPerBand, BandwidthPartInfo::UMi_StreetCanyon);
    OperationBandInfo band =
        ccBwpCreator.CreateOperationBandContiguousCc(bandConf);
    nrHelper->InitializeOperationBand(&band);
    allBwps = CcBwpCreator::GetAllBwps({band});

    nrHelper->SetBeamformingHelper(
        CreateObject<IdealBeamformingHelper>());
    nrHelper->SetSchedulerTypeId(NrMacSchedulerTdmaRR::GetTypeId());

    // ======================================================================
    // MOBILITY
    // ======================================================================

    MobilityHelper mobility;

    // -- gNBs: fixed, elevated (cell towers along highway corridor) --------
    Ptr<ListPositionAllocator> gnbPos =
        CreateObject<ListPositionAllocator>();
    gnbPos->Add(Vector(0.0,    0.0, 25.0));   // gNB-A
    gnbPos->Add(Vector(400.0,  0.0, 25.0));   // gNB-B
    gnbPos->Add(Vector(800.0,  0.0, 25.0));   // gNB-C
    gnbPos->Add(Vector(1200.0, 0.0, 25.0));   // gNB-D
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.SetPositionAllocator(gnbPos);
    mobility.Install(gnbNodes);

    // -- UEs: highway corridor, constant velocity -------------------------
    Ptr<RandomBoxPositionAllocator> uePos =
        CreateObject<RandomBoxPositionAllocator>();
    uePos->SetAttribute(
        "X", StringValue(
                 "ns3::UniformRandomVariable[Min=-200|Max=1400]"));
    uePos->SetAttribute(
        "Y", StringValue(
                 "ns3::UniformRandomVariable[Min=-30|Max=30]"));
    uePos->SetAttribute(
        "Z", StringValue(
                 "ns3::ConstantRandomVariable[Constant=1.5]"));
    mobility.SetMobilityModel("ns3::ConstantVelocityMobilityModel");
    mobility.SetPositionAllocator(uePos);
    mobility.Install(ueNodes);

    // Assign velocities: urban arterial, 8-15 m/s (29-54 km/h)
    Ptr<UniformRandomVariable> speedRng =
        CreateObject<UniformRandomVariable>();
    speedRng->SetAttribute("Min", DoubleValue(8.0));
    speedRng->SetAttribute("Max", DoubleValue(15.0));
    for (uint32_t i = 0; i < ueNodes.GetN(); i++)
    {
        Ptr<ConstantVelocityMobilityModel> mob =
            ueNodes.Get(i)->GetObject<ConstantVelocityMobilityModel>();
        double vx = speedRng->GetValue();
        mob->SetVelocity(Vector(vx, 0.0, 0.0));
    }

    // ======================================================================
    // NR DEVICE INSTALLATION
    // ======================================================================

    NetDeviceContainer gnbNetDev =
        nrHelper->InstallGnbDevice(gnbNodes, allBwps);
    NetDeviceContainer ueNetDev =
        nrHelper->InstallUeDevice(ueNodes, allBwps);

    for (auto it = gnbNetDev.Begin(); it != gnbNetDev.End(); ++it)
    {
        DynamicCast<NrGnbNetDevice>(*it)->UpdateConfig();
    }
    for (auto it = ueNetDev.Begin(); it != ueNetDev.End(); ++it)
    {
        DynamicCast<NrUeNetDevice>(*it)->UpdateConfig();
    }

    // -- IP stack for UEs (after NR devices) ------------------------------
    internet.Install(ueNodes);
    Ipv4InterfaceContainer ueIpIface =
        epcHelper->AssignUeIpv4Address(ueNetDev);

    for (uint32_t i = 0; i < ueNodes.GetN(); i++)
    {
        Ptr<Ipv4StaticRouting> ueStaticRouting =
            ipv4RoutingHelper.GetStaticRouting(
                ueNodes.Get(i)->GetObject<Ipv4>());
        ueStaticRouting->SetDefaultRoute(
            epcHelper->GetUeDefaultGatewayAddress(), 1);
    }

    // Attach each UE to the nearest gNB
    nrHelper->AttachToClosestEnb(ueNetDev, gnbNetDev);

    // ======================================================================
    // APPLICATIONS
    // ======================================================================

    uint16_t bsmPort = 1234;

    // -- BSM sink on remote host (receives all UE traffic) ----------------
    UdpServerHelper bsmSink(bsmPort);
    ApplicationContainer serverApps = bsmSink.Install(remoteHost);
    serverApps.Start(Seconds(0.5));
    serverApps.Stop(Seconds(simTime));

    // -- BsmApplication on every UE ---------------------------------------
    double bsmStartTime = 2.0;
    for (uint32_t i = 0; i < ueNodes.GetN(); i++)
    {
        Ptr<BsmApplication> bsmApp = CreateObject<BsmApplication>();

        bool isAttacker =
            hasAttacker && (i < numAttackers);
        std::string ueAttackType =
            (isAttacker && isVehicularAttack) ? attackType : "Benign";

        Time interval  = MilliSeconds(100); // 10 Hz ETSI CAM rate
        uint32_t pktSz = 200;

        // VehicularDoS: 1000 Hz (1 ms interval)
        if (ueAttackType == "VehicularDoS")
        {
            interval = MilliSeconds(1);
        }

        bsmApp->Setup(remoteHostAddr, bsmPort, interval,
                      i + 1, // vehicle ID = 1-based UE index
                      ueAttackType, pktSz);

        ueNodes.Get(i)->AddApplication(bsmApp);
        bsmApp->SetStartTime(Seconds(bsmStartTime));
        bsmApp->SetStopTime(Seconds(simTime));
    }

    // -- Network attack applications (S01-S05) ----------------------------
    if (isNetworkAttack)
    {
        // Determine flood parameters based on attack type
        uint16_t floodPort     = bsmPort;
        Time     floodInterval = MilliSeconds(2);
        uint32_t floodPktSize  = 1024;
        bool     floodIsTcp    = false;
        Time     onDuration    = Seconds(0);
        Time     offDuration   = Seconds(0);

        if (attackType == "UDPFlood")
        {
            floodPort     = bsmPort;
            floodInterval = MilliSeconds(2);   // 500 Hz
            floodPktSize  = 1024;
        }
        else if (attackType == "ICMPFlood")
        {
            floodPort     = 9;                 // discard port
            floodInterval = MilliSeconds(5);   // 200 Hz
            floodPktSize  = 64;
        }
        else if (attackType == "SYNFlood")
        {
            floodPort     = 8080;
            floodInterval = MilliSeconds(2);   // 500 Hz burst
            floodPktSize  = 64;
            onDuration    = MilliSeconds(200);
            offDuration   = MilliSeconds(50);
        }
        else if (attackType == "HTTPFlood")
        {
            floodPort     = 80;
            floodInterval = MilliSeconds(5);   // 200 Hz
            floodPktSize  = 1460;
        }
        else if (attackType == "SlowDoS")
        {
            floodPort     = 8888;
            floodInterval = MilliSeconds(50);  // 20 Hz
            floodPktSize  = 64;
            onDuration    = MilliSeconds(500);
            offDuration   = MilliSeconds(2000);
        }

        // Create UDP sink for flood traffic (if not using BSM port)
        if (floodPort != bsmPort)
        {
            UdpServerHelper floodSink(floodPort);
            ApplicationContainer sinkApp = floodSink.Install(remoteHost);
            sinkApp.Start(Seconds(0.5));
            sinkApp.Stop(Seconds(simTime));
        }

        // Install FloodApplication on all attacker nodes
        for (uint32_t a = 0; a < numAttackers; a++)
        {
            Ptr<FloodApplication> floodApp =
                CreateObject<FloodApplication>();
            floodApp->Setup(remoteHostAddr, floodPort,
                            floodInterval, floodPktSize, floodIsTcp,
                            onDuration, offDuration);
            ueNodes.Get(a)->AddApplication(floodApp);
            floodApp->SetStartTime(Seconds(5.0));
            floodApp->SetStopTime(Seconds(simTime));
        }
    }

    // ======================================================================
    // FLOW MONITOR (supplementary -- for aggregate stats)
    // ======================================================================
    FlowMonitorHelper flowHelper;
    Ptr<FlowMonitor> flowMonitor = flowHelper.InstallAll();

    // ======================================================================
    // RUN
    // ======================================================================
    Simulator::Stop(Seconds(simTime));

    std::cout << "Running " << scenario
              << " | attack=" << attackType
              << " | UEs=" << numUes
              << " | attackers=" << numAttackers
              << " | gNBs=4"
              << " | time=" << simTime << "s"
              << " | seed=" << seed << std::endl;

    Simulator::Run();

    // -- Save FlowMonitor XML ---------------------------------------------
    std::string flowmonFile = outputDir + "/flowmon_" + scenario + ".xml";
    flowMonitor->SerializeToXmlFile(flowmonFile, true, true);

    // -- Write scenario metadata JSON -------------------------------------
    std::string metaFile = outputDir + "/meta_" + scenario + ".json";
    std::ofstream meta(metaFile, std::ios::out);
    if (meta.is_open())
    {
        meta << "{\n"
             << "  \"scenario\": \"" << scenario << "\",\n"
             << "  \"attackType\": \"" << attackType << "\",\n"
             << "  \"simTime\": " << simTime << ",\n"
             << "  \"numUes\": " << numUes << ",\n"
             << "  \"numAttackers\": " << numAttackers << ",\n"
             << "  \"seed\": " << seed << ",\n"
             << "  \"isNetworkAttack\": "
             << (isNetworkAttack ? "true" : "false") << ",\n"
             << "  \"isVehicularAttack\": "
             << (isVehicularAttack ? "true" : "false") << "\n"
             << "}\n";
        meta.close();
    }

    // -- Close packet log -------------------------------------------------
    g_packetLog.close();

    std::cout << "Done. Packet log: " << logFile
              << " | FlowMonitor: " << flowmonFile << std::endl;

    Simulator::Destroy();
    return 0;
}
