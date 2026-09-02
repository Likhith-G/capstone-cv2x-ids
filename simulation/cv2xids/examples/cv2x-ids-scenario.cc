/*
 * CV2X-IDS v2 scenario: cross-layer misbehaviour dataset for NR sidelink.
 *
 * What this differs on, relative to the earlier generator, and why:
 *
 *  - Sensing and channel randomness are ON. With both off the simulation is
 *    deterministic and every vehicle in a class produces the same feature
 *    vector. That single setting is most of the reason the v1 dataset
 *    collapsed to 408 distinct rows.
 *  - Vehicles travel in both directions at individually drawn speeds and wrap
 *    around the road, so relative geometry keeps changing over a long run
 *    instead of being frozen at t=0.
 *  - Benign stations emit a MIX of CAM, DENM and CPM at ETSI-triggered,
 *    DCC-gated rates. Message type is therefore not a label.
 *  - Attack parameters are drawn per attacker instance from distributions.
 *  - Ground truth is written only on the transmit side and joined offline.
 *
 * Radio-layer attack A1 (sensing manipulation) is realised by disabling the
 * sensing procedure on the attacker's MAC and shortening its resource
 * reservation interval. The attacker still emits standards-compliant SCI and
 * PSSCH; it simply declines to cooperate in resource selection. Nothing in the
 * application content betrays it, which is the point of the cross-layer claim.
 */

#include "ns3/antenna-module.h"
#include "ns3/applications-module.h"
#include "ns3/config-store.h"
#include "ns3/core-module.h"
#include "ns3/cv2xids-module.h"
#include "ns3/internet-module.h"
#include "ns3/lte-module.h"
#include "ns3/mobility-module.h"
#include "ns3/nr-module.h"
#include "ns3/point-to-point-module.h"

#include <cmath>
#include <map>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("Cv2xIdsScenario");

namespace
{

/// Turn the "1|1|0|..." bitmap string into the vector the pool factory wants.
void
GetSlBitmapFromString(std::string slBitMapString, std::vector<std::bitset<1>>& slBitMapVector)
{
    static std::unordered_map<std::string, uint8_t> lookupTable = {
        {"0", 0},
        {"1", 1},
    };
    std::stringstream ss(slBitMapString);
    std::string token;
    std::vector<std::string> extracted;
    while (std::getline(ss, token, '|'))
    {
        extracted.push_back(token);
    }
    for (const auto& v : extracted)
    {
        if (lookupTable.find(v) == lookupTable.end())
        {
            NS_FATAL_ERROR("Bit type " << v << " not valid, only 0 and 1 are allowed");
        }
        slBitMapVector.push_back(lookupTable[v] & 0x01);
    }
}

std::string
AttackName(ItsAttack a)
{
    switch (a)
    {
    case ItsAttack::NONE: return "benign";
    case ItsAttack::POS_CONST_OFFSET: return "pos_const_offset";
    case ItsAttack::POS_RANDOM: return "pos_random";
    case ItsAttack::POS_OFFSET_RANDOM: return "pos_offset_random";
    case ItsAttack::POS_REPLAY: return "pos_replay";
    case ItsAttack::SPEED_FALSIFY: return "speed_falsify";
    case ItsAttack::SYBIL: return "sybil";
    case ItsAttack::DOS_RATE: return "dos_rate";
    case ItsAttack::SPS_MANIPULATION: return "sps_manipulation";
    case ItsAttack::FAKE_SCI: return "fake_sci";
    case ItsAttack::JAMMING: return "jamming";
    case ItsAttack::POS_SMALL_OFFSET: return "pos_small_offset";
    case ItsAttack::DOS_LOW_RATE: return "dos_low_rate";
    case ItsAttack::POS_MEDIUM_OFFSET: return "pos_medium_offset";
    }
    return "unknown";
}

} // namespace

int
main(int argc, char* argv[])
{
    // --- scenario -------------------------------------------------------
    uint16_t numLanesPerDirection = 3;
    uint16_t vehiclesPerLane = 12;
    double roadLength = 1000.0; // metres
    double laneWidth = 4.0;
    double meanSpeed = 25.0; // m/s, about 90 km/h
    double speedStdDev = 4.0;
    uint16_t numVru = 0;
    // Roadside units are the detection points and, in the federated setting,
    // the clients. They listen and never transmit, so they do not perturb the
    // channel load they are there to measure.
    uint16_t numRsu = 4;
    double rsuHeight = 5.0;
    double denmEventsPerHour = 120.0;
    // DCC is what holds channel occupancy down. Turning it off is both a way
    // to reach the congested regime deliberately and, per TS 102 687, an
    // attack surface in its own right.
    bool enableDcc = true;
    double brakeEventsPerHour = 40.0;

    // --- misbehaviour ----------------------------------------------------
    double attackerFraction = 0.30;
    std::string attackMix = "1,2,3,4,5,6,7,8"; // ItsAttack values in play
    // Fraction of the run an attacker actually attacks. Zero is continuous
    // misbehaviour, which is what every corpus so far assumed and is the
    // easiest adversary to catch.
    double sporadicDuty = 0.0;
    uint32_t rngRun = 1;

    // --- radio -----------------------------------------------------------
    double centralFrequencyBandSl = 5.89e9;
    uint16_t bandwidthBandSl = 400; // 40 MHz
    double txPower = 23;            // dBm
    std::string tddPattern = "DL|DL|DL|F|UL|UL|UL|UL|UL|UL|";
    std::string slBitMap = "1|1|1|1|1|1|0|0|0|1|1|1";
    uint16_t numerologyBwpSl = 0;
    uint16_t slSensingWindow = 100;
    uint16_t slSelectionWindow = 5;
    uint16_t slSubchannelSize = 25;
    uint16_t slMaxNumPerReserve = 3;
    double slProbResourceKeep = 0.0;
    uint16_t slMaxTxTransNumPssch = 5;
    uint16_t reservationPeriod = 100;       // ms, benign RRI
    // A1 reserves at the same interval as everyone else by default. Giving
    // attackers their own RRI turns the SCI reservation field into a perfect
    // single-feature separator, which fails validation gate 5. The aggressive
    // variant stays available but must be labelled as its own class.
    uint16_t attackerReservationPeriod = 100;
    // Benign stations do NOT all reserve at the same interval. Real ITS
    // services differ: a CAM stream at 100 ms sits alongside services that
    // reserve more or less often. Giving every benign station one RRI made the
    // SCI reservation field a perfect single-feature separator for any attack
    // that changed it, which fails validation gate 5. A spread of benign RRIs
    // is both more realistic and what turns resource-exhaustion detection into
    // an actual inference rather than a lookup.
    std::string benignRriSet = "40,100,100,100,200";
    // A2, resource exhaustion: reserve as often as the pool allows and claim
    // the maximum number of future resources per SCI. Against a benign station
    // holding one resource every 100 ms this attacker holds three every 40 ms,
    // a 7.5-fold resource footprint, without violating the protocol.
    uint16_t exhaustionRri = 40;
    uint16_t exhaustionMaxNumPerReserve = 3;
    bool enableSensing = true;
    bool enableChannelRandomness = true;
    uint16_t channelUpdatePeriod = 100; // ms
    uint16_t t1 = 2;
    uint16_t t2 = 33;
    int slThresPsschRsrp = -128;
    uint8_t mcs = 14;
    bool harqEnabled = true;

    // --- run -------------------------------------------------------------
    Time simTime = Seconds(30);
    Time slBearersActivationTime = Seconds(2.0);
    std::string outputDir = "./cv2xids-out";
    std::string simTag = "run01";

    CommandLine cmd(__FILE__);
    cmd.AddValue("numLanesPerDirection", "Lanes in each direction", numLanesPerDirection);
    cmd.AddValue("vehiclesPerLane", "Vehicles per lane", vehiclesPerLane);
    cmd.AddValue("roadLength", "Road length in metres", roadLength);
    cmd.AddValue("meanSpeed", "Mean vehicle speed in m/s", meanSpeed);
    cmd.AddValue("speedStdDev", "Standard deviation of vehicle speed in m/s", speedStdDev);
    cmd.AddValue("numVru", "Number of vulnerable road users sending VAM", numVru);
    cmd.AddValue("numRsu", "Number of roadside units, spaced evenly along the road", numRsu);
    cmd.AddValue("rsuHeight", "Roadside unit antenna height in metres", rsuHeight);
    cmd.AddValue("denmEventsPerHour", "Fallback DENM event rate when no traffic model",
                 denmEventsPerHour);
    cmd.AddValue("brakeEventsPerHour", "Mean emergency braking events per vehicle per hour",
                 brakeEventsPerHour);
    cmd.AddValue("enableDcc", "Apply TS 102 687 reactive DCC gating", enableDcc);
    cmd.AddValue("attackerFraction", "Fraction of stations that misbehave", attackerFraction);
    cmd.AddValue("sporadicDuty",
                 "Fraction of the run each attacker spends attacking, in "
                 "exponential bursts. 0 attacks continuously",
                 sporadicDuty);
    cmd.AddValue("attackMix", "Comma separated ItsAttack ids in play", attackMix);
    cmd.AddValue("rngRun", "RNG run number, this is the seed of a replicate", rngRun);
    cmd.AddValue("enableSensing", "Enable the mode 2 sensing procedure", enableSensing);
    cmd.AddValue("enableChannelRandomness", "Enable shadowing and channel updates",
                 enableChannelRandomness);
    cmd.AddValue("reservationPeriod", "Benign resource reservation interval in ms",
                 reservationPeriod);
    cmd.AddValue("attackerReservationPeriod", "Attacker RRI in ms for A1",
                 attackerReservationPeriod);
    cmd.AddValue("benignRriSet", "Comma separated benign reservation intervals in ms",
                 benignRriSet);
    cmd.AddValue("exhaustionRri", "Reservation interval used by the exhaustion attack",
                 exhaustionRri);
    cmd.AddValue("txPower", "Transmit power in dBm", txPower);
    cmd.AddValue("mcs", "Sidelink MCS", mcs);
    cmd.AddValue("slSubchannelSize", "Subchannel size in RBs", slSubchannelSize);
    cmd.AddValue("bandwidthBandSl", "Sidelink bandwidth in units of 100 kHz",
                 bandwidthBandSl);
    cmd.AddValue("simTime", "Simulation duration", simTime);
    cmd.AddValue("outputDir", "Directory for the CSV tables", outputDir);
    cmd.AddValue("simTag", "Tag identifying this run", simTag);
    cmd.Parse(argc, argv);

    NS_ABORT_IF(centralFrequencyBandSl > 6e9);

    // TS 38.214: the selection window must fit inside the reservation period.
    // The attacker reserves more aggressively than everyone else, so it is the
    // binding case.
    double selectionWindowMs = (t2 - t1 + 1) / static_cast<double>(1 << numerologyBwpSl);
    NS_ABORT_MSG_IF(attackerReservationPeriod <= selectionWindowMs,
                    "attackerReservationPeriod ("
                        << attackerReservationPeriod << " ms) must exceed the selection window ("
                        << selectionWindowMs << " ms). Lower T2 or raise the attacker RRI.");
    // NrSlCommResourcePool additionally requires the reservation period in
    // slots to be a whole number of physical sidelink pool lengths. With the
    // default 12-bit bitmap over the 10-slot TDD pattern that length is 20
    // slots, so the RRI must be a multiple of 20 ms at numerology 0.
    NS_ABORT_MSG_IF(attackerReservationPeriod % 20 != 0 || reservationPeriod % 20 != 0,
                    "Reservation periods must be a multiple of the physical sidelink pool "
                    "length in ms (20 ms for the default bitmap and TDD pattern)");

    RngSeedManager::SetSeed(1);
    RngSeedManager::SetRun(rngRun);

    Config::SetDefault("ns3::LteRlcUm::MaxTxBufferSize", UintegerValue(999999999));

    // ------------------------------------------------------------------
    // Mobility: a bidirectional highway with per-vehicle speeds.
    // ------------------------------------------------------------------
    uint32_t numVehicles = numLanesPerDirection * vehiclesPerLane * 2;
    uint32_t numMobile = numVehicles + numVru;
    NodeContainer allUes;
    allUes.Create(numMobile + numRsu);

    // Mobile stations get a velocity model; roadside units are fixed. Keeping
    // them on separate models is what stops the car-following model from
    // taking control of an RSU and driving it down the road.
    NodeContainer mobileNodes;
    NodeContainer rsuNodes;
    for (uint32_t i = 0; i < allUes.GetN(); ++i)
    {
        (i < numMobile ? mobileNodes : rsuNodes).Add(allUes.Get(i));
    }

    MobilityHelper mobility;
    mobility.SetMobilityModel("ns3::ConstantVelocityMobilityModel");
    mobility.Install(mobileNodes);

    MobilityHelper rsuMobility;
    rsuMobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    rsuMobility.Install(rsuNodes);
    for (uint32_t i = 0; i < rsuNodes.GetN(); ++i)
    {
        // Evenly spaced, offset half a spacing from the ends so no unit sits on
        // the wrap seam where a vehicle teleports.
        double spacing = roadLength / rsuNodes.GetN();
        double x = spacing * (i + 0.5);
        rsuNodes.Get(i)->GetObject<MobilityModel>()->SetPosition(
            Vector(x, 0.0, rsuHeight));
    }

    Ptr<UniformRandomVariable> posVar = CreateObject<UniformRandomVariable>();
    Ptr<NormalRandomVariable> speedVar = CreateObject<NormalRandomVariable>();
    speedVar->SetAttribute("Mean", DoubleValue(meanSpeed));
    speedVar->SetAttribute("Variance", DoubleValue(speedStdDev * speedStdDev));

    for (uint32_t i = 0; i < numVehicles; ++i)
    {
        bool eastbound = (i % 2 == 0);
        uint16_t lane = (i / 2) % numLanesPerDirection;
        double y = eastbound ? (1.0 + lane) * laneWidth : -(1.0 + lane) * laneWidth;
        // Spread vehicles along the road with jitter, so the initial geometry
        // is not a rigid grid.
        double x = posVar->GetValue(0.0, roadLength);
        // Three vehicle classes. A single speed distribution collapses under
        // car following, and with it the CAM trigger period; a mixed fleet is
        // both more realistic and keeps the trigger period spread out.
        double classDraw = posVar->GetValue(0.0, 1.0);
        double classMean = classDraw < 0.15 ? meanSpeed * 0.80   // heavy goods
                           : classDraw < 0.35 ? meanSpeed * 0.92 // vans
                                              : meanSpeed * 1.12; // cars
        speedVar->SetAttribute("Mean", DoubleValue(classMean));
        double v = std::max(5.0, speedVar->GetValue());

        Ptr<ConstantVelocityMobilityModel> mm =
            allUes.Get(i)->GetObject<ConstantVelocityMobilityModel>();
        mm->SetPosition(Vector(x, y, 1.6));
        mm->SetVelocity(Vector(eastbound ? v : -v, 0.0, 0.0));
    }
    for (uint32_t i = numVehicles; i < numMobile; ++i)
    {
        // VRUs walk along the verge.
        Ptr<ConstantVelocityMobilityModel> mm =
            allUes.Get(i)->GetObject<ConstantVelocityMobilityModel>();
        mm->SetPosition(Vector(posVar->GetValue(0.0, roadLength),
                               posVar->GetValue(-2.0, 2.0) > 0 ? 12.0 : -12.0,
                               1.5));
        mm->SetVelocity(Vector(posVar->GetValue(0.8, 1.6), 0.0, 0.0));
    }

    // Car-following dynamics. Constant velocity made the ETSI CAM triggers
    // fire at a fixed period, which is a degeneracy, so vehicles are handed to
    // an IDM model that also produces genuine hard braking for DENM.
    Ptr<HighwayTrafficModel> traffic = CreateObject<HighwayTrafficModel>();
    traffic->SetAttribute("BrakeEventsPerHour", DoubleValue(brakeEventsPerHour));
    traffic->Install(mobileNodes, roadLength);

    // ------------------------------------------------------------------
    // NR stack
    // ------------------------------------------------------------------
    Ptr<NrPointToPointEpcHelper> epcHelper = CreateObject<NrPointToPointEpcHelper>();
    Ptr<NrHelper> nrHelper = CreateObject<NrHelper>();
    nrHelper->SetEpcHelper(epcHelper);

    BandwidthPartInfoPtrVector allBwps;
    CcBwpCreator ccBwpCreator;
    const uint8_t numCcPerBand = 1;
    CcBwpCreator::SimpleOperationBandConf bandConfSl(centralFrequencyBandSl,
                                                     bandwidthBandSl,
                                                     numCcPerBand,
                                                     BandwidthPartInfo::V2V_Highway);
    OperationBandInfo bandSl = ccBwpCreator.CreateOperationBandContiguousCc(bandConfSl);

    if (enableChannelRandomness)
    {
        Config::SetDefault("ns3::ThreeGppChannelModel::UpdatePeriod",
                           TimeValue(MilliSeconds(channelUpdatePeriod)));
        nrHelper->SetChannelConditionModelAttribute("UpdatePeriod",
                                                    TimeValue(MilliSeconds(channelUpdatePeriod)));
        nrHelper->SetPathlossAttribute("ShadowingEnabled", BooleanValue(true));
    }
    else
    {
        Config::SetDefault("ns3::ThreeGppChannelModel::UpdatePeriod", TimeValue(MilliSeconds(0)));
        nrHelper->SetChannelConditionModelAttribute("UpdatePeriod", TimeValue(MilliSeconds(0)));
        nrHelper->SetPathlossAttribute("ShadowingEnabled", BooleanValue(false));
    }

    nrHelper->InitializeOperationBand(&bandSl);
    allBwps = CcBwpCreator::GetAllBwps({bandSl});

    nrHelper->SetUeAntennaAttribute("NumRows", UintegerValue(1));
    nrHelper->SetUeAntennaAttribute("NumColumns", UintegerValue(2));
    nrHelper->SetUeAntennaAttribute("AntennaElement",
                                    PointerValue(CreateObject<IsotropicAntennaModel>()));
    nrHelper->SetUePhyAttribute("TxPower", DoubleValue(txPower));

    nrHelper->SetUeMacTypeId(NrSlUeMac::GetTypeId());
    nrHelper->SetUeMacAttribute("EnableSensing", BooleanValue(enableSensing));
    nrHelper->SetUeMacAttribute("T1", UintegerValue(static_cast<uint8_t>(t1)));
    nrHelper->SetUeMacAttribute("T2", UintegerValue(t2));
    nrHelper->SetUeMacAttribute("ActivePoolId", UintegerValue(0));
    nrHelper->SetUeMacAttribute("SlThresPsschRsrp", IntegerValue(slThresPsschRsrp));

    uint8_t bwpIdForGbrMcptt = 0;
    nrHelper->SetBwpManagerTypeId(TypeId::LookupByName("ns3::NrSlBwpManagerUe"));
    nrHelper->SetUeBwpManagerAlgorithmAttribute("GBR_MC_PUSH_TO_TALK",
                                                UintegerValue(bwpIdForGbrMcptt));
    std::set<uint8_t> bwpIdContainer;
    bwpIdContainer.insert(bwpIdForGbrMcptt);

    NetDeviceContainer allUesNetDev = nrHelper->InstallUeDevice(allUes, allBwps);
    for (auto it = allUesNetDev.Begin(); it != allUesNetDev.End(); ++it)
    {
        DynamicCast<NrUeNetDevice>(*it)->UpdateConfig();
    }

    Ptr<NrSlHelper> nrSlHelper = CreateObject<NrSlHelper>();
    nrSlHelper->SetEpcHelper(epcHelper);
    nrSlHelper->SetSlErrorModel("ns3::NrEesmIrT1");
    nrSlHelper->SetUeSlAmcAttribute("AmcModel", EnumValue(NrAmc::ErrorModel));
    nrSlHelper->SetNrSlSchedulerTypeId(NrSlUeMacSchedulerFixedMcs::GetTypeId());
    nrSlHelper->SetUeSlSchedulerAttribute("Mcs", UintegerValue(mcs));
    nrSlHelper->PrepareUeForSidelink(allUesNetDev, bwpIdContainer);

    // ---- sidelink pre-configuration ----------------------------------
    Ptr<NrSlCommResourcePoolFactory> ptrFactory = Create<NrSlCommResourcePoolFactory>();
    std::vector<std::bitset<1>> slBitMapVector;
    GetSlBitmapFromString(slBitMap, slBitMapVector);
    NS_ABORT_MSG_IF(slBitMapVector.empty(), "GetSlBitmapFromString failed");
    ptrFactory->SetSlTimeResources(slBitMapVector);
    ptrFactory->SetSlSensingWindow(slSensingWindow);
    ptrFactory->SetSlSelectionWindow(slSelectionWindow);
    ptrFactory->SetSlFreqResourcePscch(10);
    ptrFactory->SetSlSubchannelSize(slSubchannelSize);
    ptrFactory->SetSlMaxNumPerReserve(
        std::max<uint16_t>(slMaxNumPerReserve, exhaustionMaxNumPerReserve));
    std::vector<uint16_t> benignRris;
    {
        std::stringstream rs(benignRriSet);
        std::string tok;
        while (std::getline(rs, tok, ','))
        {
            if (!tok.empty())
            {
                uint16_t v = static_cast<uint16_t>(std::stoi(tok));
                NS_ABORT_MSG_IF(v % 20 != 0 || v <= selectionWindowMs,
                                "benign RRI " << v << " ms must be a multiple of the 20 ms "
                                "physical pool length and exceed the selection window");
                benignRris.push_back(v);
            }
        }
    }
    NS_ABORT_MSG_IF(benignRris.empty(), "benignRriSet must name at least one interval");

    std::set<uint16_t> rsvpSet = {0, attackerReservationPeriod, reservationPeriod, exhaustionRri};
    rsvpSet.insert(benignRris.begin(), benignRris.end());
    std::list<uint16_t> rsvpList(rsvpSet.begin(), rsvpSet.end());
    ptrFactory->SetSlResourceReservePeriodList(rsvpList);
    LteRrcSap::SlResourcePoolNr slResourcePoolNr = ptrFactory->CreatePool();

    LteRrcSap::SlResourcePoolConfigNr slresoPoolConfigNr;
    slresoPoolConfigNr.haveSlResourcePoolConfigNr = true;
    LteRrcSap::SlResourcePoolIdNr slResourcePoolIdNr;
    slResourcePoolIdNr.id = 0;
    slresoPoolConfigNr.slResourcePoolId = slResourcePoolIdNr;
    slresoPoolConfigNr.slResourcePool = slResourcePoolNr;

    LteRrcSap::SlBwpPoolConfigCommonNr slBwpPoolConfigCommonNr;
    slBwpPoolConfigCommonNr.slTxPoolSelectedNormal[slResourcePoolIdNr.id] = slresoPoolConfigNr;

    LteRrcSap::Bwp bwp;
    bwp.numerology = numerologyBwpSl;
    bwp.symbolsPerSlots = 14;
    bwp.rbPerRbg = 1;
    bwp.bandwidth = bandwidthBandSl;

    LteRrcSap::SlBwpGeneric slBwpGeneric;
    slBwpGeneric.bwp = bwp;
    slBwpGeneric.slLengthSymbols = LteRrcSap::GetSlLengthSymbolsEnum(14);
    slBwpGeneric.slStartSymbol = LteRrcSap::GetSlStartSymbolEnum(0);

    LteRrcSap::SlBwpConfigCommonNr slBwpConfigCommonNr;
    slBwpConfigCommonNr.haveSlBwpGeneric = true;
    slBwpConfigCommonNr.slBwpGeneric = slBwpGeneric;
    slBwpConfigCommonNr.haveSlBwpPoolConfigCommonNr = true;
    slBwpConfigCommonNr.slBwpPoolConfigCommonNr = slBwpPoolConfigCommonNr;

    LteRrcSap::SlFreqConfigCommonNr slFreConfigCommonNr;
    for (const auto& it : bwpIdContainer)
    {
        slFreConfigCommonNr.slBwpList[it] = slBwpConfigCommonNr;
    }

    LteRrcSap::TddUlDlConfigCommon tddUlDlConfigCommon;
    tddUlDlConfigCommon.tddPattern = tddPattern;
    LteRrcSap::SlPreconfigGeneralNr slPreconfigGeneralNr;
    slPreconfigGeneralNr.slTddConfig = tddUlDlConfigCommon;

    LteRrcSap::SlUeSelectedConfig slUeSelectedPreConfig;
    slUeSelectedPreConfig.slProbResourceKeep = slProbResourceKeep;
    LteRrcSap::SlPsschTxParameters psschParams;
    psschParams.slMaxTxTransNumPssch = static_cast<uint8_t>(slMaxTxTransNumPssch);
    LteRrcSap::SlPsschTxConfigList pscchTxConfigList;
    pscchTxConfigList.slPsschTxParameters[0] = psschParams;
    slUeSelectedPreConfig.slPsschTxConfigList = pscchTxConfigList;

    LteRrcSap::SidelinkPreconfigNr slPreConfigNr;
    slPreConfigNr.slPreconfigGeneral = slPreconfigGeneralNr;
    slPreConfigNr.slUeSelectedPreConfig = slUeSelectedPreConfig;
    slPreConfigNr.slPreconfigFreqInfoList[0] = slFreConfigCommonNr;
    nrSlHelper->InstallNrSlPreConfiguration(allUesNetDev, slPreConfigNr);

    int64_t stream = 1;
    stream += nrHelper->AssignStreams(allUesNetDev, stream);
    stream += nrSlHelper->AssignStreams(allUesNetDev, stream);

    // ------------------------------------------------------------------
    // Assign misbehaviour. Every attacker draws its own parameters, so two
    // attackers of the same class do not produce identical feature vectors.
    // ------------------------------------------------------------------
    std::vector<int> mix;
    {
        std::stringstream ss(attackMix);
        std::string tok;
        while (std::getline(ss, tok, ','))
        {
            if (!tok.empty())
            {
                mix.push_back(std::stoi(tok));
            }
        }
    }
    NS_ABORT_MSG_IF(mix.empty(), "attackMix must name at least one attack");

    stream += traffic->AssignStreams(stream);
    traffic->Start();

    Ptr<UniformRandomVariable> pick = CreateObject<UniformRandomVariable>();
    pick->SetStream(stream++);

    std::vector<ItsAttack> assigned(allUes.GetN(), ItsAttack::NONE);
    for (uint32_t i = 0; i < allUes.GetN(); ++i)
    {
        if (i >= numVehicles)
        {
            continue; // VRUs and roadside units stay benign in this scenario
        }
        if (pick->GetValue(0.0, 1.0) < attackerFraction)
        {
            assigned[i] = static_cast<ItsAttack>(mix[pick->GetInteger(0, mix.size() - 1)]);
        }
    }

    // ------------------------------------------------------------------
    // Internet stack and sidelink bearers.
    //
    // Two bearers are activated. Benign stations reserve at the normal RRI.
    // A1 attackers reserve far more aggressively and, below, have sensing
    // switched off on their MAC. Both remain standards compliant.
    // ------------------------------------------------------------------
    InternetStackHelper internet;
    internet.Install(allUes);
    stream += internet.AssignStreams(allUes, stream);

    uint32_t dstL2Id = 255;
    Ipv4Address groupAddress4("225.0.0.0");
    uint16_t port = 8000;

    epcHelper->AssignUeIpv4Address(allUesNetDev);
    Ipv4StaticRoutingHelper ipv4RoutingHelper;
    for (uint32_t u = 0; u < allUes.GetN(); ++u)
    {
        Ptr<Ipv4StaticRouting> ueStaticRouting =
            ipv4RoutingHelper.GetStaticRouting(allUes.Get(u)->GetObject<Ipv4>());
        ueStaticRouting->SetDefaultRoute(epcHelper->GetUeDefaultGatewayAddress(), 1);
    }

    // One transmit bearer per distinct reservation interval in use.
    std::map<uint16_t, NetDeviceContainer> txGroups;
    Ptr<UniformRandomVariable> rriPick = CreateObject<UniformRandomVariable>();
    rriPick->SetStream(stream++);

    for (uint32_t i = 0; i < allUes.GetN(); ++i)
    {
        if (i >= numMobile)
        {
            continue; // a roadside unit receives only, so it gets no TX bearer
        }
        uint16_t rri;
        if (assigned[i] == ItsAttack::FAKE_SCI)
        {
            rri = exhaustionRri;
        }
        else if (assigned[i] == ItsAttack::SPS_MANIPULATION)
        {
            rri = attackerReservationPeriod;
        }
        else
        {
            rri = benignRris[rriPick->GetInteger(0, benignRris.size() - 1)];
        }
        txGroups[rri].Add(allUes.Get(i)->GetDevice(0));
    }

    auto makeTft = [&](LteSlTft::Direction dir, uint16_t rri) {
        SidelinkInfo slInfo;
        slInfo.m_castType = SidelinkInfo::CastType::Groupcast;
        slInfo.m_dstL2Id = dstL2Id;
        slInfo.m_rri = MilliSeconds(rri);
        slInfo.m_dynamic = false;
        slInfo.m_pdb = Seconds(0);
        slInfo.m_harqEnabled = harqEnabled;
        return Create<LteSlTft>(dir, groupAddress4, slInfo);
    };

    for (const auto& kv : txGroups)
    {
        nrSlHelper->ActivateNrSlBearer(slBearersActivationTime,
                                       kv.second,
                                       makeTft(LteSlTft::Direction::TRANSMIT, kv.first));
        std::cout << "  TX bearer: RRI " << kv.first << " ms for " << kv.second.GetN()
                  << " stations" << std::endl;
    }
    nrSlHelper->ActivateNrSlBearer(slBearersActivationTime,
                                   allUesNetDev,
                                   makeTft(LteSlTft::Direction::RECEIVE, reservationPeriod));

    // A1: the attacker's MAC stops sensing. It selects resources without
    // regard to what its neighbours have reserved, which shows up as
    // collisions and PRR loss around it, and in nothing it says.
    for (uint32_t i = 0; i < allUes.GetN(); ++i)
    {
        if (assigned[i] != ItsAttack::SPS_MANIPULATION)
        {
            continue;
        }
        Ptr<NrUeNetDevice> dev = DynamicCast<NrUeNetDevice>(allUes.Get(i)->GetDevice(0));
        Ptr<NrUeMac> mac = dev->GetMac(bwpIdForGbrMcptt);
        mac->SetAttribute("EnableSensing", BooleanValue(false));
    }

    // ------------------------------------------------------------------
    // Instrumentation and applications
    // ------------------------------------------------------------------
    Cv2xIdsHelper::EnableTraces(outputDir, simTag);

    // The slot duration follows the numerology: 1 ms at numerology 0.
    Time slotDuration = MilliSeconds(1) / (1 << numerologyBwpSl);
    // bandwidthBandSl is in units of 100 kHz. One resource block is 12
    // subcarriers at the numerology's subcarrier spacing.
    double bandwidthHz = bandwidthBandSl * 100e3;
    double scsHz = 15e3 * (1 << numerologyBwpSl);
    uint16_t totalRbs = static_cast<uint16_t>(bandwidthHz / (12.0 * scsHz));
    uint16_t totalSubchannels = totalRbs / slSubchannelSize;
    NS_ABORT_MSG_IF(totalSubchannels == 0,
                    "Subchannel size " << slSubchannelSize << " RBs does not fit in "
                                       << totalRbs << " RBs of bandwidth");
    std::cout << "Pool geometry: " << totalRbs << " RBs, " << totalSubchannels
              << " subchannels of " << slSubchannelSize << " RBs, slot "
              << slotDuration.GetMicroSeconds() << " us" << std::endl;
    // Sidelink lives only in the uplink slots the TDD pattern allows, masked
    // again by the pool's time bitmap. Both fractions multiply.
    size_t ulSlots = 0, patternSlots = 0;
    {
        std::stringstream ps(tddPattern);
        std::string tok;
        while (std::getline(ps, tok, '|'))
        {
            if (tok.empty())
            {
                continue;
            }
            patternSlots++;
            // Only uplink slots carry sidelink. Counting flexible slots as
            // usable gives 0.525, against 0.42 measured from the slot indices
            // the MAC actually used; excluding them gives 0.45, which matches.
            if (tok == "UL")
            {
                ulSlots++;
            }
        }
    }
    size_t onBits = 0;
    for (const auto& b : slBitMapVector)
    {
        onBits += b.count();
    }
    double slotFraction = (patternSlots ? double(ulSlots) / patternSlots : 1.0) *
                          (slBitMapVector.size() ? double(onBits) / slBitMapVector.size() : 1.0);
    std::cout << "Sidelink slot fraction: " << slotFraction << " (" << ulSlots << "/"
              << patternSlots << " TDD x " << onBits << "/" << slBitMapVector.size()
              << " bitmap)" << std::endl;
    Cv2xIdsHelper::InstallChannelMonitors(allUes, totalSubchannels, slotDuration, slotFraction);

    Cv2xTraceStore::Get().Open("tx", ItsStationApp::TxHeader());
    Cv2xTraceStore::Get().Open("rx_app", ItsStationApp::RxHeader());

    Address remoteAddress = InetSocketAddress(groupAddress4, port);
    ApplicationContainer apps;
    for (uint32_t i = 0; i < allUes.GetN(); ++i)
    {
        Ptr<ItsStationApp> app = CreateObject<ItsStationApp>();
        app->SetAttribute("Remote", AddressValue(remoteAddress));
        app->SetAttribute("StationId", UintegerValue(1000 + i));
        app->SetAttribute("PlaygroundX", DoubleValue(roadLength));
        app->SetAttribute("PlaygroundY", DoubleValue(laneWidth * (numLanesPerDirection + 2)));
        bool isRsu = i >= numMobile;
        app->SetAttribute("IsRsu", BooleanValue(isRsu));
        app->SetAttribute("IsVru", BooleanValue(!isRsu && i >= numVehicles));
        app->SetAttribute("DenmEventsPerHour", DoubleValue(denmEventsPerHour));
        app->SetAttribute("EnableDcc", BooleanValue(enableDcc));
        app->SetAttribute("SporadicDuty", DoubleValue(sporadicDuty));
        app->SetAttack(assigned[i]);
        stream += app->AssignStreams(stream);
        allUes.Get(i)->AddApplication(app);
        apps.Add(app);

        Cv2xIdsHelper::RecordStation(allUes.Get(i)->GetId(),
                                     1000 + i,
                                     isRsu ? "rsu" : (i >= numVehicles ? "vru" : "vehicle"),
                                     static_cast<int>(assigned[i]),
                                     AttackName(assigned[i]));
    }
    apps.Start(slBearersActivationTime + Seconds(0.1));
    apps.Stop(simTime);

    Cv2xIdsHelper::ConnectRadioTraces();
    Cv2xIdsHelper::ScheduleFlush(Seconds(1));

    Simulator::Stop(simTime);
    Simulator::Run();

    std::cout << "stations            : " << numVehicles << " vehicles, " << numVru
              << " VRU, " << numRsu << " RSU" << std::endl;
    std::cout << "tx app messages     : " << Cv2xTraceStore::Get().Rows("tx") << std::endl;
    std::cout << "rx app messages     : " << Cv2xTraceStore::Get().Rows("rx_app") << std::endl;
    std::cout << "rx PSCCH records    : " << Cv2xTraceStore::Get().Rows("rx_pscch") << std::endl;
    std::cout << "rx PSSCH records    : " << Cv2xTraceStore::Get().Rows("rx_pssch") << std::endl;
    std::cout << "tx PSCCH records    : " << Cv2xTraceStore::Get().Rows("tx_pscch") << std::endl;
    std::cout << "tx PSSCH records    : " << Cv2xTraceStore::Get().Rows("tx_pssch") << std::endl;

    Cv2xIdsHelper::Close();
    Simulator::Destroy();
    return 0;
}
