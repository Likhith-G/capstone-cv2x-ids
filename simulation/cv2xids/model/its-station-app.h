/*
 * CV2X-IDS: ETSI ITS station application.
 *
 * Generates CAM, DENM, CPM and VAM according to the ETSI generation rules
 * rather than at a fixed rate, applies TS 102 687 reactive DCC gating, and
 * optionally misbehaves.
 *
 * Two properties matter for dataset validity:
 *
 *  1. Benign traffic is a MIX of message types at LOAD-DEPENDENT rates. In the
 *     earlier dataset every benign packet was an identical periodic BSM, so any
 *     non-BSM packet was by construction an attack and the classifier learned
 *     a type marker rather than a behaviour.
 *
 *  2. Ground truth never leaves this class over the air. It is written to the
 *     transmit-side log and joined offline on the message uid. See
 *     its-message-header.h.
 */
#ifndef CV2X_ITS_STATION_APP_H
#define CV2X_ITS_STATION_APP_H

#include "its-message-header.h"
#include "highway-traffic-model.h"
#include "sl-channel-monitor.h"

#include "ns3/application.h"
#include "ns3/constant-velocity-mobility-model.h"
#include "ns3/nstime.h"
#include "ns3/random-variable-stream.h"
#include "ns3/socket.h"

#include <deque>
#include <vector>

namespace ns3
{

/// Misbehaviour implemented at the application layer. Radio-layer attacks
/// (SPS manipulation, fake SCI, jamming) are configured on the MAC and PHY and
/// only appear here as a label.
enum class ItsAttack : uint8_t
{
    NONE = 0,
    POS_CONST_OFFSET = 1,  //!< claimed position displaced by a fixed vector
    POS_RANDOM = 2,        //!< claimed position uniform over the playground
    POS_OFFSET_RANDOM = 3, //!< fresh random displacement every message
    POS_REPLAY = 4,        //!< the station's own earlier position, replayed
    SPEED_FALSIFY = 5,     //!< claimed speed scaled by a factor
    SYBIL = 6,             //!< one radio, several claimed identities
    DOS_RATE = 7,          //!< ETSI generation rules ignored, fixed high rate
    // 8..15 reserved for radio-layer attacks, labelled by the scenario
    SPS_MANIPULATION = 8,
    FAKE_SCI = 9,
    JAMMING = 10,
    // Stealthy variants. The same mechanisms, tuned to perturb the observables
    // as little as an attacker can while still achieving something. A dataset
    // whose attacks are all blatant overstates what a detector can do, so the
    // paper reports the degradation from the loud variant to the quiet one.
    POS_SMALL_OFFSET = 11, //!< a few metres of displacement, not hundreds
    DOS_LOW_RATE = 12,     //!< a modest rate increase, not a flood
    // The middle of the magnitude ladder. POS_SMALL_OFFSET sits inside the
    // benign positioning error and POS_CONST_OFFSET sits far outside it, so
    // without this class the dataset has no attack in the range where
    // detection is actually decided.
    POS_MEDIUM_OFFSET = 13,
};

class ItsStationApp : public Application
{
  public:
    static TypeId GetTypeId();
    ItsStationApp();
    ~ItsStationApp() override;

    void SetRemote(Address addr);
    void SetStationId(uint32_t id);
    uint32_t GetStationId() const;
    void SetAttack(ItsAttack a);
    ItsAttack GetAttack() const;

    /// Assign the streams used by this application's random variables.
    int64_t AssignStreams(int64_t stream);

    /// Column headers for the two tables this application writes.
    static std::string TxHeader();
    static std::string RxHeader();

  protected:
    void DoDispose() override;

  private:
    void StartApplication() override;
    void StopApplication() override;

    /// T_CheckCamGen, every 100 ms per EN 302 637-2 section 6.1.3.
    void CheckCamGeneration();
    void CheckOtherGeneration();
    void SendMessage(ItsMsgType type);
    void HandleRead(Ptr<Socket> socket);

    /// True kinematic state read from the mobility model.
    void ReadTrueState(Vector& pos, double& speed, double& heading) const;

    /// Turn the true state into the state this station will claim.
    void ApplyAttack(const Vector& truePos,
                     double trueSpeed,
                     double trueHeading,
                     uint32_t& claimedStationId,
                     Vector& claimedPos,
                     double& claimedSpeed,
                     double& claimedHeading);

    /// TS 102 687 reactive DCC: minimum inter-CAM time for the current CBR.
    Time DccMinInterval() const;

    Ptr<Socket> m_socket;
    Address m_peer;
    uint16_t m_port{8000};
    uint32_t m_stationId{0};
    uint32_t m_packetSize{200}; //!< payload bytes beyond the ITS header
    ItsAttack m_attack{ItsAttack::NONE};
    Ptr<SlChannelMonitor> m_monitor;
    Ptr<VehicleDynamics> m_dynamics;

    // --- ETSI EN 302 637-2 CAM generation state --------------------------
    Time m_tCheckCamGen{MilliSeconds(100)};
    Time m_tGenCamMin{MilliSeconds(100)};
    Time m_tGenCamMax{MilliSeconds(1000)};
    Time m_tGenCam{MilliSeconds(1000)}; //!< current dynamics-driven interval
    uint8_t m_nGenCam{3};               //!< N_GenCam, section 6.1.3
    uint8_t m_camsSinceTrigger{0};
    Time m_lastCamTime{Seconds(-1)};
    Vector m_lastCamPos{0, 0, 0};
    double m_lastCamSpeed{0.0};
    double m_lastCamHeading{0.0};
    bool m_firstCamSent{false};

    double m_headingThresholdDeg{4.0}; //!< EN 302 637-2 trigger thresholds
    double m_positionThresholdM{4.0};
    double m_speedThresholdMps{0.5};

    bool m_enableDcc{true};

    // --- other message types ---------------------------------------------
    bool m_isVru{false};
    /// A roadside unit listens and never originates CAM, VAM or CPM. It is the
    /// detection point, not a participant in the traffic it observes.
    bool m_isRsu{false};
    bool m_enableDenm{true};
    bool m_enableCpm{true};
    double m_denmEventsPerHour{6.0};
    Time m_denmRepeatInterval{MilliSeconds(1000)};
    Time m_denmDuration{Seconds(5)};
    Time m_denmActiveUntil{Seconds(-1)};
    Time m_lastDenmTime{Seconds(-1)};
    Time m_lastCpmTime{Seconds(-1)};
    Time m_lastVamTime{Seconds(-1)};
    uint32_t m_lastNeighbourCount{0};

    // --- attack parameters, all drawn per instance ------------------------
    Ptr<RandomVariableStream> m_offsetX;
    Ptr<RandomVariableStream> m_offsetY;
    Ptr<RandomVariableStream> m_speedFactor;
    Ptr<UniformRandomVariable> m_uniform;
    double m_drawnOffsetX{0.0};
    double m_drawnOffsetY{0.0};
    double m_drawnSpeedFactor{1.0};
    Time m_replayDelay{Seconds(3)};
    uint32_t m_sybilIdentities{4};
    double m_sybilSpreadMin{40.0};
    double m_sybilSpreadMax{200.0};
    Time m_dosInterval{MilliSeconds(10)};
    double m_smallOffsetMin{4.0};
    double m_smallOffsetMax{25.0};
    double m_mediumOffsetMin{50.0};
    double m_mediumOffsetMax{80.0};
    Time m_lowRateIntervalMin{MilliSeconds(40)};
    Time m_lowRateIntervalMax{MilliSeconds(80)};
    double m_playgroundX{2000.0};
    double m_playgroundY{100.0};

    // --- sporadic misbehaviour -------------------------------------------
    // An attacker that misbehaves continuously is the easiest one to catch,
    // and it is the only one the corpus contains. A station that lies for a
    // few seconds and then tells the truth for a while attacks the persistence
    // rule directly, because that rule asks whether a station looked wrong in
    // several of its recent windows, and it is trivially available to a real
    // attacker. Duty is the fraction of time spent attacking; zero means
    // always on, which is the behaviour every earlier corpus has.
    double m_sporadicDuty{0.0};
    Time m_sporadicMeanBurst{Seconds(3)};
    bool m_attackActive{true};
    EventId m_sporadicEvent;

    // --- benign GNSS error, VeReMi Extension form -------------------------
    // Every broadcast position carries receiver error, because a benign
    // vehicle that claims its exact true position is a vehicle no positioning
    // system produces. Without this the application-layer self-consistency
    // features are measured against a benign class with zero variance, and any
    // attack larger than zero is separable in principle.
    //
    // Per vehicle and per axis k in {east, north}:
    //   E_0     ~ U(-A, A)
    //   mu_t    = (E_0 + E_{t-1}) / 2
    //   sigma   = c * |E_0|
    //   E_t     ~ N(mu_t, sigma^2)
    // plus a Poisson multipath spike of standard deviation m_gnssSpikeSigma at
    // rate m_gnssSpikeRate per second. A is 5 m and c is 0.03 for the highway
    // scenario, which are the VeReMi Extension values.
    bool m_gnssError{true};
    double m_gnssMaxInitial{5.0};
    double m_gnssJitter{0.03};
    double m_gnssSpikeSigma{5.0};
    double m_gnssSpikeRate{0.005};
    double m_speedErrSigma{0.00016};
    double m_headingErrMaxDeg{20.0};
    Time m_gnssTick{MilliSeconds(100)};
    double m_gnssE0x{0.0}, m_gnssE0y{0.0};
    double m_gnssEx{0.0}, m_gnssEy{0.0};
    double m_gnssSigmaX{0.0}, m_gnssSigmaY{0.0};
    double m_speedErrRel{0.0};
    double m_headingErr0{0.0};
    Ptr<NormalRandomVariable> m_gnssNormal;
    EventId m_gnssEvent;

    /// Recent true positions, for the replay attack. Bounded by m_replayDelay.
    std::deque<std::pair<Time, Vector>> m_positionHistory;

    /// One sequence counter per claimed identity, so a Sybil's identities each
    /// carry a plausible independent sequence.
    std::vector<uint32_t> m_seqPerIdentity;

    EventId m_camEvent;
    EventId m_otherEvent;
    void InitSporadic();
    void ToggleSporadic();
    void InitGnssError();
    void StepGnssError();
    void ApplyGnssError(Vector& pos, double& speed, double& heading) const;
    bool m_running{false};

    static uint64_t s_nextMsgUid;
};

} // namespace ns3

#endif /* CV2X_ITS_STATION_APP_H */
