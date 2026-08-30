/*
 * CV2X-IDS: ETSI ITS message header carried over NR sidelink.
 *
 * DESIGN INVARIANT (do not break, it is what keeps the dataset honest):
 * this header carries ONLY what a real receiver could observe. No ground
 * truth, no attacker flag, no true kinematics. Truth is written by the
 * transmitter into its own log and joined offline on m_msgUid. A feature
 * extractor that only reads the receive-side tables therefore CANNOT
 * construct an oracle feature, which is the defect that invalidated v1.
 */
#ifndef CV2X_ITS_MESSAGE_HEADER_H
#define CV2X_ITS_MESSAGE_HEADER_H

#include "ns3/header.h"
#include "ns3/vector.h"

namespace ns3
{

/// ETSI ITS message types. Values follow the ITS-AID / message id conventions.
enum class ItsMsgType : uint8_t
{
    DENM = 1,  //!< EN 302 637-3
    CAM = 2,   //!< EN 302 637-2
    CPM = 14,  //!< TS 103 324
    VAM = 16,  //!< TS 103 300-3
    MCM = 20,  //!< TR 103 578 / TS 103 561
};

/**
 * \brief The observable content of an ETSI ITS message.
 *
 * Kinematic fields are the CLAIMED values. For a benign station they equal the
 * true state; for a misbehaving station they do not. The receiver cannot tell
 * the difference, which is the whole point.
 */
class ItsMessageHeader : public Header
{
  public:
    ItsMessageHeader();
    static TypeId GetTypeId();
    TypeId GetInstanceTypeId() const override;
    void Print(std::ostream& os) const override;
    uint32_t GetSerializedSize() const override;
    void Serialize(Buffer::Iterator start) const override;
    uint32_t Deserialize(Buffer::Iterator start) override;

    /// Globally unique message id. Join key between the Tx truth log and every
    /// receive-side table. It is an identifier, never a feature.
    void SetMsgUid(uint64_t uid);
    uint64_t GetMsgUid() const;

    void SetMsgType(ItsMsgType t);
    ItsMsgType GetMsgType() const;

    /// The claimed ITS station id (pseudonym). A Sybil attacker varies this.
    void SetStationId(uint32_t id);
    uint32_t GetStationId() const;

    /// Per-claimed-identity message counter, as a real CAM sequence would be.
    void SetSeqNo(uint32_t s);
    uint32_t GetSeqNo() const;

    /// Claimed generation time, milliseconds since simulation start.
    void SetGenTimeMs(double t);
    double GetGenTimeMs() const;

    void SetPosition(const Vector& p);
    Vector GetPosition() const;

    void SetSpeed(double mps);
    double GetSpeed() const;

    /// Claimed heading in degrees clockwise from north, per EN 302 637-2.
    void SetHeading(double deg);
    double GetHeading() const;

    void SetAcceleration(double mps2);
    double GetAcceleration() const;

    /// Number of perceived objects. Meaningful for CPM, zero otherwise.
    void SetPerceivedObjects(uint16_t n);
    uint16_t GetPerceivedObjects() const;

  private:
    uint64_t m_msgUid{0};
    uint8_t m_msgType{static_cast<uint8_t>(ItsMsgType::CAM)};
    uint32_t m_stationId{0};
    uint32_t m_seqNo{0};
    double m_genTimeMs{0.0};
    double m_posX{0.0};
    double m_posY{0.0};
    double m_posZ{0.0};
    double m_speed{0.0};
    double m_heading{0.0};
    double m_accel{0.0};
    uint16_t m_perceivedObjects{0};
};

} // namespace ns3

#endif /* CV2X_ITS_MESSAGE_HEADER_H */
