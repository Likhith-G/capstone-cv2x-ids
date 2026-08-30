/*
 * CV2X-IDS: microscopic highway traffic on a wrapped road.
 *
 * WHY THIS EXISTS. Constant-velocity mobility makes the ETSI CAM triggering
 * rules deterministic: a vehicle moving at a fixed v crosses the 4 m position
 * threshold every 4/v seconds exactly, so its CAM interval is a constant and
 * every vehicle at the same speed produces the same feature vector. A first
 * run confirmed it, with 2484 of 2700 benign CAM intervals landing on exactly
 * 200 ms. That is the earlier degeneracy arriving through a different door.
 *
 * Car-following dynamics fix it at the source. Speeds vary continuously, so
 * the speed-delta and position-delta triggers fire irregularly, and genuine
 * hard braking exists for DENM to report. It also removes the SUMO dependency.
 *
 * Model: the Intelligent Driver Model of Treiber, Hennecke and Helbing,
 * "Congested traffic states in empirical observations and microscopic
 * simulations", Physical Review E 62(2), 2000. Longitudinal only; lane
 * changing is deliberately out of scope.
 */
#ifndef CV2X_HIGHWAY_TRAFFIC_MODEL_H
#define CV2X_HIGHWAY_TRAFFIC_MODEL_H

#include "ns3/node-container.h"
#include "ns3/nstime.h"
#include "ns3/object.h"
#include "ns3/random-variable-stream.h"

#include <vector>

namespace ns3
{

/**
 * \brief Per-vehicle longitudinal state, aggregated onto the node so the ITS
 * application can read its own acceleration without reaching into the model.
 */
class VehicleDynamics : public Object
{
  public:
    static TypeId GetTypeId();
    double GetAcceleration() const;
    void SetAcceleration(double a);
    /// True while this vehicle is braking hard enough to warrant a DENM.
    bool IsHardBraking() const;
    void SetHardBraking(bool b);

  private:
    double m_accel{0.0};
    bool m_hardBraking{false};
};

class HighwayTrafficModel : public Object
{
  public:
    static TypeId GetTypeId();
    HighwayTrafficModel();
    ~HighwayTrafficModel() override;

    /**
     * \brief Take control of a set of vehicles already placed by a mobility helper.
     * \param nodes the vehicle nodes, each with a ConstantVelocityMobilityModel
     * \param roadLength length of the wrapped road in metres
     */
    void Install(const NodeContainer& nodes, double roadLength);

    /// Begin stepping the model.
    void Start();

    int64_t AssignStreams(int64_t stream);

  private:
    void Step();

    struct Vehicle
    {
        Ptr<Node> node;
        Ptr<VehicleDynamics> dynamics;
        double desiredSpeed; //!< v0
        double speed;        //!< v
        double maxAccel;     //!< a, lower for heavy vehicles
        double comfortDecel; //!< b
        int direction;       //!< +1 eastbound, -1 westbound
        int lane;
        double brakeUntil; //!< simulation time in seconds a forced brake ends
    };

    std::vector<Vehicle> m_vehicles;
    double m_roadLength{1000.0};
    Time m_step{MilliSeconds(100)};

    // IDM parameters. Defaults are the values used in the original paper for a
    // highway scenario.
    double m_maxAccel{1.4};       //!< a, m/s^2
    double m_comfortDecel{2.0};   //!< b, m/s^2
    double m_minGap{2.0};         //!< s0, m
    double m_desiredTimeGap{1.5}; //!< T, s
    double m_delta{4.0};          //!< acceleration exponent
    double m_vehicleLength{5.0};  //!< m

    /// Mean number of emergency braking events per vehicle per hour. These are
    /// what a DENM legitimately reports.
    double m_brakeEventsPerHour{40.0};
    double m_brakeDecel{6.0};   //!< m/s^2 during a forced brake
    Time m_brakeDuration{MilliSeconds(1500)};
    double m_hardBrakeThreshold{3.0}; //!< m/s^2, above which a DENM is warranted

    Ptr<UniformRandomVariable> m_uniform;
    bool m_running{false};
};

} // namespace ns3

#endif /* CV2X_HIGHWAY_TRAFFIC_MODEL_H */
