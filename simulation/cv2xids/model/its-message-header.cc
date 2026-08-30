#include "its-message-header.h"

#include "ns3/log.h"

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("ItsMessageHeader");
NS_OBJECT_ENSURE_REGISTERED(ItsMessageHeader);

ItsMessageHeader::ItsMessageHeader()
{
}

TypeId
ItsMessageHeader::GetTypeId()
{
    static TypeId tid = TypeId("ns3::ItsMessageHeader")
                            .SetParent<Header>()
                            .SetGroupName("Cv2xIds")
                            .AddConstructor<ItsMessageHeader>();
    return tid;
}

TypeId
ItsMessageHeader::GetInstanceTypeId() const
{
    return GetTypeId();
}

void
ItsMessageHeader::Print(std::ostream& os) const
{
    os << "uid=" << m_msgUid << " type=" << +m_msgType << " station=" << m_stationId
       << " seq=" << m_seqNo << " pos=(" << m_posX << "," << m_posY << ")"
       << " speed=" << m_speed << " heading=" << m_heading;
}

uint32_t
ItsMessageHeader::GetSerializedSize() const
{
    // 8 + 1 + 4 + 4 + 8*6 + 2 = 67 bytes.
    return 8 + 1 + 4 + 4 + 8 + 8 + 8 + 8 + 8 + 8 + 8 + 2;
}

void
ItsMessageHeader::Serialize(Buffer::Iterator start) const
{
    start.WriteHtonU64(m_msgUid);
    start.WriteU8(m_msgType);
    start.WriteHtonU32(m_stationId);
    start.WriteHtonU32(m_seqNo);
    start.WriteHtonU64(*reinterpret_cast<const uint64_t*>(&m_genTimeMs));
    start.WriteHtonU64(*reinterpret_cast<const uint64_t*>(&m_posX));
    start.WriteHtonU64(*reinterpret_cast<const uint64_t*>(&m_posY));
    start.WriteHtonU64(*reinterpret_cast<const uint64_t*>(&m_posZ));
    start.WriteHtonU64(*reinterpret_cast<const uint64_t*>(&m_speed));
    start.WriteHtonU64(*reinterpret_cast<const uint64_t*>(&m_heading));
    start.WriteHtonU64(*reinterpret_cast<const uint64_t*>(&m_accel));
    start.WriteHtonU16(m_perceivedObjects);
}

uint32_t
ItsMessageHeader::Deserialize(Buffer::Iterator start)
{
    m_msgUid = start.ReadNtohU64();
    m_msgType = start.ReadU8();
    m_stationId = start.ReadNtohU32();
    m_seqNo = start.ReadNtohU32();
    uint64_t raw;
    raw = start.ReadNtohU64();
    m_genTimeMs = *reinterpret_cast<double*>(&raw);
    raw = start.ReadNtohU64();
    m_posX = *reinterpret_cast<double*>(&raw);
    raw = start.ReadNtohU64();
    m_posY = *reinterpret_cast<double*>(&raw);
    raw = start.ReadNtohU64();
    m_posZ = *reinterpret_cast<double*>(&raw);
    raw = start.ReadNtohU64();
    m_speed = *reinterpret_cast<double*>(&raw);
    raw = start.ReadNtohU64();
    m_heading = *reinterpret_cast<double*>(&raw);
    raw = start.ReadNtohU64();
    m_accel = *reinterpret_cast<double*>(&raw);
    m_perceivedObjects = start.ReadNtohU16();
    return GetSerializedSize();
}

void ItsMessageHeader::SetMsgUid(uint64_t uid) { m_msgUid = uid; }
uint64_t ItsMessageHeader::GetMsgUid() const { return m_msgUid; }

void ItsMessageHeader::SetMsgType(ItsMsgType t) { m_msgType = static_cast<uint8_t>(t); }
ItsMsgType ItsMessageHeader::GetMsgType() const { return static_cast<ItsMsgType>(m_msgType); }

void ItsMessageHeader::SetStationId(uint32_t id) { m_stationId = id; }
uint32_t ItsMessageHeader::GetStationId() const { return m_stationId; }

void ItsMessageHeader::SetSeqNo(uint32_t s) { m_seqNo = s; }
uint32_t ItsMessageHeader::GetSeqNo() const { return m_seqNo; }

void ItsMessageHeader::SetGenTimeMs(double t) { m_genTimeMs = t; }
double ItsMessageHeader::GetGenTimeMs() const { return m_genTimeMs; }

void ItsMessageHeader::SetPosition(const Vector& p) { m_posX = p.x; m_posY = p.y; m_posZ = p.z; }
Vector ItsMessageHeader::GetPosition() const { return Vector(m_posX, m_posY, m_posZ); }

void ItsMessageHeader::SetSpeed(double mps) { m_speed = mps; }
double ItsMessageHeader::GetSpeed() const { return m_speed; }

void ItsMessageHeader::SetHeading(double deg) { m_heading = deg; }
double ItsMessageHeader::GetHeading() const { return m_heading; }

void ItsMessageHeader::SetAcceleration(double a) { m_accel = a; }
double ItsMessageHeader::GetAcceleration() const { return m_accel; }

void ItsMessageHeader::SetPerceivedObjects(uint16_t n) { m_perceivedObjects = n; }
uint16_t ItsMessageHeader::GetPerceivedObjects() const { return m_perceivedObjects; }

} // namespace ns3
