#include "its-station-app.h"

#include "cv2x-trace-store.h"

#include "ns3/boolean.h"
#include "ns3/double.h"
#include "ns3/inet-socket-address.h"
#include "ns3/inet6-socket-address.h"
#include "ns3/log.h"
#include "ns3/mobility-model.h"
#include "ns3/node.h"
#include "ns3/packet.h"
#include "ns3/pointer.h"
#include "ns3/simulator.h"
#include "ns3/string.h"
#include "ns3/udp-socket-factory.h"
#include "ns3/uinteger.h"

#include <cmath>
#include <sstream>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("ItsStationApp");
NS_OBJECT_ENSURE_REGISTERED(ItsStationApp);

uint64_t ItsStationApp::s_nextMsgUid = 1;

namespace
{
/// Heading in degrees clockwise from north, per EN 302 637-2.
double
HeadingFromVelocity(const Vector& v)
{
    if (std::fabs(v.x) < 1e-9 && std::fabs(v.y) < 1e-9)
    {
        return 0.0;
    }
    double deg = std::atan2(v.x, v.y) * 180.0 / M_PI;
    return deg < 0.0 ? deg + 360.0 : deg;
}

double
AngleDiffDeg(double a, double b)
{
    double d = std::fabs(a - b);
    return d > 180.0 ? 360.0 - d : d;
}
} // namespace

TypeId
ItsStationApp::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::ItsStationApp")
            .SetParent<Application>()
            .SetGroupName("Cv2xIds")
            .AddConstructor<ItsStationApp>()
            .AddAttribute("Remote",
                          "The groupcast address messages are sent to",
                          AddressValue(),
                          MakeAddressAccessor(&ItsStationApp::m_peer),
                          MakeAddressChecker())
            .AddAttribute("StationId",
                          "The genuine ITS station id of this station",
                          UintegerValue(0),
                          MakeUintegerAccessor(&ItsStationApp::m_stationId),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("PacketSize",
                          "Payload bytes carried in addition to the ITS header",
                          UintegerValue(200),
                          MakeUintegerAccessor(&ItsStationApp::m_packetSize),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("EnableDcc",
                          "Apply TS 102 687 reactive DCC gating to CAM generation",
                          BooleanValue(true),
                          MakeBooleanAccessor(&ItsStationApp::m_enableDcc),
                          MakeBooleanChecker())
            .AddAttribute("IsRsu",
                          "This station is a roadside unit: it receives and logs but "
                          "never originates CAM, VAM or CPM",
                          BooleanValue(false),
                          MakeBooleanAccessor(&ItsStationApp::m_isRsu),
                          MakeBooleanChecker())
            .AddAttribute("IsVru",
                          "This station is a vulnerable road user and sends VAM, not CAM",
                          BooleanValue(false),
                          MakeBooleanAccessor(&ItsStationApp::m_isVru),
                          MakeBooleanChecker())
            .AddAttribute("EnableDenm",
                          "Generate event-triggered DENM",
                          BooleanValue(true),
                          MakeBooleanAccessor(&ItsStationApp::m_enableDenm),
                          MakeBooleanChecker())
            .AddAttribute("EnableCpm",
                          "Generate collective perception messages",
                          BooleanValue(true),
                          MakeBooleanAccessor(&ItsStationApp::m_enableCpm),
                          MakeBooleanChecker())
            .AddAttribute("DenmEventsPerHour",
                          "Mean rate of DENM-triggering events for this station",
                          DoubleValue(6.0),
                          MakeDoubleAccessor(&ItsStationApp::m_denmEventsPerHour),
                          MakeDoubleChecker<double>())
            .AddAttribute("ReplayDelay",
                          "How far back the replay attack reaches",
                          TimeValue(Seconds(3)),
                          MakeTimeAccessor(&ItsStationApp::m_replayDelay),
                          MakeTimeChecker())
            .AddAttribute("SybilIdentities",
                          "Number of identities a Sybil attacker claims",
                          UintegerValue(4),
                          MakeUintegerAccessor(&ItsStationApp::m_sybilIdentities),
                          MakeUintegerChecker<uint32_t>(1, 64))
            .AddAttribute("SybilSpreadMin",
                          "Closest a Sybil ghost is placed to the attacker, in metres",
                          DoubleValue(40.0),
                          MakeDoubleAccessor(&ItsStationApp::m_sybilSpreadMin),
                          MakeDoubleChecker<double>())
            .AddAttribute("SybilSpreadMax",
                          "Furthest a Sybil ghost is placed from the attacker, in metres",
                          DoubleValue(200.0),
                          MakeDoubleAccessor(&ItsStationApp::m_sybilSpreadMax),
                          MakeDoubleChecker<double>())
            .AddAttribute("SmallOffsetMin",
                          "Smallest displacement the stealthy position attack uses, in metres",
                          DoubleValue(4.0),
                          MakeDoubleAccessor(&ItsStationApp::m_smallOffsetMin),
                          MakeDoubleChecker<double>())
            .AddAttribute("SmallOffsetMax",
                          "Largest displacement the stealthy position attack uses, in metres",
                          DoubleValue(25.0),
                          MakeDoubleAccessor(&ItsStationApp::m_smallOffsetMax),
                          MakeDoubleChecker<double>())
            .AddAttribute("LowRateIntervalMin",
                          "Shortest inter-message time the stealthy rate attack uses",
                          TimeValue(MilliSeconds(40)),
                          MakeTimeAccessor(&ItsStationApp::m_lowRateIntervalMin),
                          MakeTimeChecker())
            .AddAttribute("LowRateIntervalMax",
                          "Longest inter-message time the stealthy rate attack uses",
                          TimeValue(MilliSeconds(80)),
                          MakeTimeAccessor(&ItsStationApp::m_lowRateIntervalMax),
                          MakeTimeChecker())
            .AddAttribute("DosInterval",
                          "Fixed inter-message time used by the rate attack",
                          TimeValue(MilliSeconds(10)),
                          MakeTimeAccessor(&ItsStationApp::m_dosInterval),
                          MakeTimeChecker())
            .AddAttribute("OffsetX",
                          "Distribution the constant position offset in x is drawn from",
                          StringValue("ns3::UniformRandomVariable[Min=-250.0|Max=250.0]"),
                          MakePointerAccessor(&ItsStationApp::m_offsetX),
                          MakePointerChecker<RandomVariableStream>())
            .AddAttribute("OffsetY",
                          "Distribution the constant position offset in y is drawn from",
                          StringValue("ns3::UniformRandomVariable[Min=-30.0|Max=30.0]"),
                          MakePointerAccessor(&ItsStationApp::m_offsetY),
                          MakePointerChecker<RandomVariableStream>())
            .AddAttribute("SpeedFactor",
                          "Distribution the claimed-speed multiplier is drawn from",
                          StringValue("ns3::UniformRandomVariable[Min=0.3|Max=2.5]"),
                          MakePointerAccessor(&ItsStationApp::m_speedFactor),
                          MakePointerChecker<RandomVariableStream>())
            .AddAttribute("PlaygroundX",
                          "Extent of the scenario in x, used by the random position attack",
                          DoubleValue(2000.0),
                          MakeDoubleAccessor(&ItsStationApp::m_playgroundX),
                          MakeDoubleChecker<double>())
            .AddAttribute("PlaygroundY",
                          "Extent of the scenario in y, used by the random position attack",
                          DoubleValue(100.0),
                          MakeDoubleAccessor(&ItsStationApp::m_playgroundY),
                          MakeDoubleChecker<double>());
    return tid;
}

ItsStationApp::ItsStationApp()
{
    m_uniform = CreateObject<UniformRandomVariable>();
}

ItsStationApp::~ItsStationApp()
{
}

void
ItsStationApp::DoDispose()
{
    m_socket = nullptr;
    Application::DoDispose();
}

void ItsStationApp::SetRemote(Address addr) { m_peer = addr; }
void ItsStationApp::SetStationId(uint32_t id) { m_stationId = id; }
uint32_t ItsStationApp::GetStationId() const { return m_stationId; }
void ItsStationApp::SetAttack(ItsAttack a) { m_attack = a; }
ItsAttack ItsStationApp::GetAttack() const { return m_attack; }

int64_t
ItsStationApp::AssignStreams(int64_t stream)
{
    m_offsetX->SetStream(stream);
    m_offsetY->SetStream(stream + 1);
    m_speedFactor->SetStream(stream + 2);
    m_uniform->SetStream(stream + 3);
    return 4;
}

std::string
ItsStationApp::TxHeader()
{
    return "msgUid,txTimeMs,txNodeId,trueStationId,claimedStationId,msgType,seqNo,"
           "trueX,trueY,trueSpeed,trueHeading,"
           "claimedX,claimedY,claimedSpeed,claimedHeading,"
           "attackId,txCbr";
}

std::string
ItsStationApp::RxHeader()
{
    return "msgUid,rxTimeMs,rxNodeId,claimedStationId,msgType,seqNo,genTimeMs,"
           "claimedX,claimedY,claimedSpeed,claimedHeading,perceivedObjects,"
           "rxX,rxY,rxSpeed,rxHeading,rxCbr,rxNeighbours";
}

void
ItsStationApp::StartApplication()
{
    NS_LOG_FUNCTION(this);
    m_running = true;

    m_monitor = GetNode()->GetObject<SlChannelMonitor>();
    m_dynamics = GetNode()->GetObject<VehicleDynamics>();

    if (!m_socket)
    {
        m_socket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
        if (InetSocketAddress::IsMatchingType(m_peer))
        {
            m_socket->Bind(InetSocketAddress(Ipv4Address::GetAny(), m_port));
        }
        else
        {
            m_socket->Bind(Inet6SocketAddress(Ipv6Address::GetAny(), m_port));
        }
        m_socket->Connect(m_peer);
        m_socket->SetAllowBroadcast(true);
        m_socket->SetRecvCallback(MakeCallback(&ItsStationApp::HandleRead, this));
    }

    // Draw this instance's attack parameters once, so that two attackers with
    // the same attack type still behave differently. Constant parameters
    // across attacker instances is what collapsed the earlier dataset to 408
    // distinct feature vectors.
    m_drawnOffsetX = m_offsetX->GetValue();
    m_drawnOffsetY = m_offsetY->GetValue();
    m_drawnSpeedFactor = m_speedFactor->GetValue();

    if (m_attack == ItsAttack::POS_SMALL_OFFSET)
    {
        // A displacement a driver could plausibly be wrong about: enough to
        // claim the next lane or a car length of gap, not enough to move the
        // received power measurably.
        double mag = m_uniform->GetValue(m_smallOffsetMin, m_smallOffsetMax);
        double ang = m_uniform->GetValue(0.0, 2.0 * M_PI);
        m_drawnOffsetX = mag * std::cos(ang);
        m_drawnOffsetY = mag * std::sin(ang) * 0.4;
    }
    else if (m_attack == ItsAttack::DOS_LOW_RATE)
    {
        m_dosInterval = MilliSeconds(m_uniform->GetInteger(
            m_lowRateIntervalMin.GetMilliSeconds(), m_lowRateIntervalMax.GetMilliSeconds()));
    }

    m_seqPerIdentity.assign(m_attack == ItsAttack::SYBIL ? m_sybilIdentities : 1, 0);

    // Stagger the first check so stations do not all evaluate the trigger in
    // the same slot.
    if (m_isRsu)
    {
        // Nothing to schedule. The receive callback is already armed, and an
        // RSU that transmitted would change the very channel load it is there
        // to measure.
        return;
    }
    Time jitter = MilliSeconds(m_uniform->GetInteger(0, 99));
    m_camEvent = Simulator::Schedule(jitter, &ItsStationApp::CheckCamGeneration, this);
    m_otherEvent = Simulator::Schedule(jitter + MilliSeconds(50),
                                       &ItsStationApp::CheckOtherGeneration,
                                       this);
}

void
ItsStationApp::StopApplication()
{
    m_running = false;
    Simulator::Cancel(m_camEvent);
    Simulator::Cancel(m_otherEvent);
    if (m_socket)
    {
        m_socket->Close();
    }
}

void
ItsStationApp::ReadTrueState(Vector& pos, double& speed, double& heading) const
{
    Ptr<MobilityModel> mm = GetNode()->GetObject<MobilityModel>();
    NS_ASSERT_MSG(mm, "ItsStationApp needs a mobility model on its node");
    pos = mm->GetPosition();
    Vector v = mm->GetVelocity();
    speed = std::sqrt(v.x * v.x + v.y * v.y);
    heading = HeadingFromVelocity(v);
}

Time
ItsStationApp::DccMinInterval() const
{
    if (!m_enableDcc || !m_monitor)
    {
        return m_tGenCamMin;
    }
    // ETSI TS 102 687 reactive DCC, state thresholds as tabulated in
    // TR 101 613. The CBR bands map to a minimum inter-packet time; the
    // relaxed state is the ETSI default of 100 ms.
    double cbr = m_monitor->GetCbr();
    if (cbr < 0.30)
    {
        return MilliSeconds(100); // relaxed
    }
    if (cbr < 0.40)
    {
        return MilliSeconds(200); // active 1
    }
    if (cbr < 0.50)
    {
        return MilliSeconds(400); // active 2
    }
    if (cbr < 0.65)
    {
        return MilliSeconds(500); // active 3
    }
    return MilliSeconds(1000); // restrictive
}

void
ItsStationApp::CheckCamGeneration()
{
    if (!m_running)
    {
        return;
    }

    Time now = Simulator::Now();
    Vector pos;
    double speed;
    double heading;
    ReadTrueState(pos, speed, heading);

    m_positionHistory.emplace_back(now, pos);
    while (!m_positionHistory.empty() && now - m_positionHistory.front().first > m_replayDelay * 2)
    {
        m_positionHistory.pop_front();
    }

    if (m_attack == ItsAttack::DOS_RATE || m_attack == ItsAttack::DOS_LOW_RATE)
    {
        // The rate attacker ignores the ETSI rules entirely. This is an
        // application-layer flood, distinct from the MAC-layer SPS attack.
        SendMessage(m_isVru ? ItsMsgType::VAM : ItsMsgType::CAM);
        m_camEvent = Simulator::Schedule(m_dosInterval, &ItsStationApp::CheckCamGeneration, this);
        return;
    }

    if (!m_isVru)
    {
        Time sinceLast = now - m_lastCamTime;
        Time minInterval = std::max(m_tGenCamMin, DccMinInterval());

        if (!m_firstCamSent)
        {
            SendMessage(ItsMsgType::CAM);
        }
        else if (sinceLast >= minInterval)
        {
            bool dynamicsTrigger =
                AngleDiffDeg(heading, m_lastCamHeading) > m_headingThresholdDeg ||
                CalculateDistance(pos, m_lastCamPos) > m_positionThresholdM ||
                std::fabs(speed - m_lastCamSpeed) > m_speedThresholdMps;

            if (dynamicsTrigger)
            {
                // EN 302 637-2 section 6.1.3: a dynamics trigger fixes
                // T_GenCam at the elapsed interval, and the next N_GenCam CAMs
                // reuse it before the station falls back to T_GenCamMax.
                m_tGenCam = std::min(sinceLast, m_tGenCamMax);
                m_camsSinceTrigger = 0;
                SendMessage(ItsMsgType::CAM);
            }
            else if (sinceLast >= std::max(m_tGenCam, minInterval) &&
                     m_camsSinceTrigger < m_nGenCam)
            {
                m_camsSinceTrigger++;
                SendMessage(ItsMsgType::CAM);
            }
            else if (sinceLast >= std::max(m_tGenCamMax, minInterval))
            {
                m_tGenCam = m_tGenCamMax;
                SendMessage(ItsMsgType::CAM);
            }
        }
    }
    else
    {
        // TS 103 300-3 VAM: 0.2 to 10 Hz. Use the same dynamics logic with a
        // wider maximum interval.
        Time sinceLast = now - m_lastVamTime;
        Time minInterval = std::max(m_tGenCamMin, DccMinInterval());
        bool trigger = !m_firstCamSent || sinceLast >= Seconds(5) ||
                       (sinceLast >= minInterval &&
                        (CalculateDistance(pos, m_lastCamPos) > m_positionThresholdM ||
                         AngleDiffDeg(heading, m_lastCamHeading) > m_headingThresholdDeg));
        if (trigger)
        {
            SendMessage(ItsMsgType::VAM);
        }
    }

    m_camEvent = Simulator::Schedule(m_tCheckCamGen, &ItsStationApp::CheckCamGeneration, this);
}

void
ItsStationApp::CheckOtherGeneration()
{
    if (!m_running)
    {
        return;
    }
    Time now = Simulator::Now();

    if (m_enableDenm)
    {
        if (now < m_denmActiveUntil)
        {
            if (now - m_lastDenmTime >= m_denmRepeatInterval)
            {
                SendMessage(ItsMsgType::DENM);
            }
        }
        else if (m_dynamics && m_dynamics->IsHardBraking())
        {
            // A real hazard: this vehicle is braking hard. EN 302 637-3 calls
            // for a DENM here, repeated until the situation clears.
            m_denmActiveUntil = now + m_denmDuration;
            SendMessage(ItsMsgType::DENM);
        }
        else if (!m_dynamics)
        {
            // No traffic model installed, so fall back to Poisson arrivals
            // thinned to this 100 ms check.
            double pEvent = m_denmEventsPerHour / 3600.0 * 0.1;
            if (m_uniform->GetValue(0.0, 1.0) < pEvent)
            {
                m_denmActiveUntil = now + m_denmDuration;
                SendMessage(ItsMsgType::DENM);
            }
        }
    }

    if (m_enableCpm && m_monitor && !m_isVru)
    {
        // TS 103 324: quasi-periodic between 1 and 10 Hz, driven by the set of
        // perceived objects. Neighbour count stands in for perception here,
        // and a change in that set shortens the interval.
        uint32_t n = m_monitor->GetNeighbourCount();
        Time sinceLast = now - m_lastCpmTime;
        // TS 103 324: quasi-periodic between 1 and 10 Hz. The interval shortens
        // only when the perceived set has grown MEANINGFULLY since the last CPM
        // was actually sent. The baseline must therefore be updated on send,
        // not on every check, or the short interval applies almost always.
        // A relative test, not an absolute one. In a dense platoon the
        // neighbour count fluctuates by one or two every window, so an
        // absolute threshold keeps the short interval permanently armed.
        double base = std::max<double>(m_lastNeighbourCount, 1);
        bool perceptionChanged = std::fabs(static_cast<double>(n) - base) / base > 0.25;
        Time interval = perceptionChanged ? MilliSeconds(100) : MilliSeconds(1000);
        if (n > 0 && sinceLast >= std::max(interval, DccMinInterval()))
        {
            m_lastNeighbourCount = n;
            SendMessage(ItsMsgType::CPM);
        }
    }

    m_otherEvent = Simulator::Schedule(MilliSeconds(100),
                                       &ItsStationApp::CheckOtherGeneration,
                                       this);
}

void
ItsStationApp::ApplyAttack(const Vector& truePos,
                           double trueSpeed,
                           double trueHeading,
                           uint32_t& claimedStationId,
                           Vector& claimedPos,
                           double& claimedSpeed,
                           double& claimedHeading)
{
    claimedStationId = m_stationId;
    claimedPos = truePos;
    claimedSpeed = trueSpeed;
    claimedHeading = trueHeading;

    switch (m_attack)
    {
    case ItsAttack::POS_CONST_OFFSET:
    case ItsAttack::POS_SMALL_OFFSET:
        claimedPos.x += m_drawnOffsetX;
        claimedPos.y += m_drawnOffsetY;
        break;

    case ItsAttack::POS_RANDOM:
        claimedPos.x = m_uniform->GetValue(0.0, m_playgroundX);
        claimedPos.y = m_uniform->GetValue(-m_playgroundY, m_playgroundY);
        break;

    case ItsAttack::POS_OFFSET_RANDOM:
        claimedPos.x += m_offsetX->GetValue();
        claimedPos.y += m_offsetY->GetValue();
        break;

    case ItsAttack::POS_REPLAY: {
        // A genuine replay: an earlier true position of this same station,
        // reported as current. The earlier "replay" resent a live position and
        // was therefore indistinguishable from benign traffic.
        Time cutoff = Simulator::Now() - m_replayDelay;
        for (auto it = m_positionHistory.begin(); it != m_positionHistory.end(); ++it)
        {
            if (it->first >= cutoff)
            {
                claimedPos = it->second;
                break;
            }
        }
        break;
    }

    case ItsAttack::SPEED_FALSIFY:
        claimedSpeed = trueSpeed * m_drawnSpeedFactor;
        break;

    case ItsAttack::SYBIL: {
        // One radio, several claimed identities. Each identity is offset in a
        // different direction so the set looks like separate vehicles, which
        // is what makes the shared RSRP signature the giveaway.
        uint32_t idx = m_uniform->GetInteger(0, m_sybilIdentities - 1);
        claimedStationId = m_stationId * 1000 + idx;
        // The ghosts are spread far enough down the road to be useful to the
        // attacker. A Sybil that plants its phantoms within a car length of
        // itself achieves nothing: the point is to fake a queue or an occupied
        // lane, which needs tens of metres of separation. It is also what
        // makes the radio voiceprint diagnostic, since identities claiming to
        // be 100 m apart have no business arriving at identical power.
        double angle = 2.0 * M_PI * idx / static_cast<double>(m_sybilIdentities);
        double radius = m_sybilSpreadMin +
                        (m_sybilSpreadMax - m_sybilSpreadMin) * idx /
                            std::max(1.0, static_cast<double>(m_sybilIdentities) - 1.0);
        claimedPos.x += radius * std::cos(angle);
        claimedPos.y += 0.3 * radius * std::sin(angle);
        break;
    }

    case ItsAttack::NONE:
    case ItsAttack::DOS_RATE:
    case ItsAttack::DOS_LOW_RATE:
    case ItsAttack::SPS_MANIPULATION:
    case ItsAttack::FAKE_SCI:
    case ItsAttack::JAMMING:
    default:
        // Radio-layer attacks send truthful application content. That is the
        // point: they are invisible to an application-only detector.
        break;
    }
}

void
ItsStationApp::SendMessage(ItsMsgType type)
{
    Time now = Simulator::Now();
    Vector truePos;
    double trueSpeed;
    double trueHeading;
    ReadTrueState(truePos, trueSpeed, trueHeading);

    uint32_t claimedStationId;
    Vector claimedPos;
    double claimedSpeed;
    double claimedHeading;
    ApplyAttack(truePos,
                trueSpeed,
                trueHeading,
                claimedStationId,
                claimedPos,
                claimedSpeed,
                claimedHeading);

    uint32_t identityIdx = 0;
    if (m_attack == ItsAttack::SYBIL)
    {
        identityIdx = claimedStationId % 1000;
        if (identityIdx >= m_seqPerIdentity.size())
        {
            identityIdx = 0;
        }
    }
    uint32_t seq = ++m_seqPerIdentity[identityIdx];

    ItsMessageHeader hdr;
    uint64_t uid = s_nextMsgUid++;
    hdr.SetMsgUid(uid);
    hdr.SetMsgType(type);
    hdr.SetStationId(claimedStationId);
    hdr.SetSeqNo(seq);
    hdr.SetGenTimeMs(now.GetSeconds() * 1000.0);
    hdr.SetPosition(claimedPos);
    hdr.SetSpeed(claimedSpeed);
    hdr.SetHeading(claimedHeading);
    hdr.SetAcceleration(m_dynamics ? m_dynamics->GetAcceleration() : 0.0);
    hdr.SetPerceivedObjects(type == ItsMsgType::CPM && m_monitor
                                ? static_cast<uint16_t>(m_monitor->GetNeighbourCount())
                                : 0);

    Ptr<Packet> p = Create<Packet>(m_packetSize);
    p->AddHeader(hdr);
    m_socket->Send(p);

    double cbr = m_monitor ? m_monitor->GetCbr() : 0.0;

    std::ostringstream row;
    row << uid << ',' << now.GetSeconds() * 1000.0 << ',' << GetNode()->GetId() << ','
        << m_stationId << ',' << claimedStationId << ',' << static_cast<int>(type) << ',' << seq
        << ',' << truePos.x << ',' << truePos.y << ',' << trueSpeed << ',' << trueHeading << ','
        << claimedPos.x << ',' << claimedPos.y << ',' << claimedSpeed << ',' << claimedHeading
        << ',' << static_cast<int>(m_attack) << ',' << cbr;
    Cv2xTraceStore::Get().Write("tx", row.str());

    if (type == ItsMsgType::CAM || type == ItsMsgType::VAM)
    {
        m_lastCamTime = now;
        m_lastVamTime = now;
        m_lastCamPos = truePos;
        m_lastCamSpeed = trueSpeed;
        m_lastCamHeading = trueHeading;
        m_firstCamSent = true;
    }
    else if (type == ItsMsgType::DENM)
    {
        m_lastDenmTime = now;
    }
    else if (type == ItsMsgType::CPM)
    {
        m_lastCpmTime = now;
    }
}

void
ItsStationApp::HandleRead(Ptr<Socket> socket)
{
    Ptr<Packet> packet;
    Address from;
    while ((packet = socket->RecvFrom(from)))
    {
        if (packet->GetSize() == 0)
        {
            break;
        }
        ItsMessageHeader hdr;
        if (packet->RemoveHeader(hdr) == 0)
        {
            continue;
        }

        Vector myPos;
        double mySpeed;
        double myHeading;
        ReadTrueState(myPos, mySpeed, myHeading);

        Vector cp = hdr.GetPosition();
        double cbr = m_monitor ? m_monitor->GetCbr() : 0.0;
        uint32_t nb = m_monitor ? m_monitor->GetNeighbourCount() : 0;

        std::ostringstream row;
        row << hdr.GetMsgUid() << ',' << Simulator::Now().GetSeconds() * 1000.0 << ','
            << GetNode()->GetId() << ',' << hdr.GetStationId() << ','
            << static_cast<int>(hdr.GetMsgType()) << ',' << hdr.GetSeqNo() << ','
            << hdr.GetGenTimeMs() << ',' << cp.x << ',' << cp.y << ',' << hdr.GetSpeed() << ','
            << hdr.GetHeading() << ',' << hdr.GetPerceivedObjects() << ',' << myPos.x << ','
            << myPos.y << ',' << mySpeed << ',' << myHeading << ',' << cbr << ',' << nb;
        Cv2xTraceStore::Get().Write("rx_app", row.str());
    }
}

} // namespace ns3
