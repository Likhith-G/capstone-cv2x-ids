#include "highway-traffic-model.h"

#include "ns3/constant-velocity-mobility-model.h"
#include "ns3/double.h"
#include "ns3/log.h"
#include "ns3/simulator.h"

#include <algorithm>
#include <cmath>
#include <map>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("HighwayTrafficModel");
NS_OBJECT_ENSURE_REGISTERED(VehicleDynamics);
NS_OBJECT_ENSURE_REGISTERED(HighwayTrafficModel);

TypeId
VehicleDynamics::GetTypeId()
{
    static TypeId tid = TypeId("ns3::VehicleDynamics")
                            .SetParent<Object>()
                            .SetGroupName("Cv2xIds")
                            .AddConstructor<VehicleDynamics>();
    return tid;
}

double VehicleDynamics::GetAcceleration() const { return m_accel; }
void VehicleDynamics::SetAcceleration(double a) { m_accel = a; }
bool VehicleDynamics::IsHardBraking() const { return m_hardBraking; }
void VehicleDynamics::SetHardBraking(bool b) { m_hardBraking = b; }

TypeId
HighwayTrafficModel::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::HighwayTrafficModel")
            .SetParent<Object>()
            .SetGroupName("Cv2xIds")
            .AddConstructor<HighwayTrafficModel>()
            .AddAttribute("Step",
                          "Interval between traffic updates",
                          TimeValue(MilliSeconds(100)),
                          MakeTimeAccessor(&HighwayTrafficModel::m_step),
                          MakeTimeChecker())
            .AddAttribute("MaxAccel",
                          "IDM maximum acceleration a in m/s^2",
                          DoubleValue(1.4),
                          MakeDoubleAccessor(&HighwayTrafficModel::m_maxAccel),
                          MakeDoubleChecker<double>())
            .AddAttribute("ComfortDecel",
                          "IDM comfortable deceleration b in m/s^2",
                          DoubleValue(2.0),
                          MakeDoubleAccessor(&HighwayTrafficModel::m_comfortDecel),
                          MakeDoubleChecker<double>())
            .AddAttribute("MinGap",
                          "IDM minimum bumper to bumper gap s0 in m",
                          DoubleValue(2.0),
                          MakeDoubleAccessor(&HighwayTrafficModel::m_minGap),
                          MakeDoubleChecker<double>())
            .AddAttribute("DesiredTimeGap",
                          "IDM desired time headway T in s",
                          DoubleValue(1.5),
                          MakeDoubleAccessor(&HighwayTrafficModel::m_desiredTimeGap),
                          MakeDoubleChecker<double>())
            .AddAttribute("BrakeEventsPerHour",
                          "Mean emergency braking events per vehicle per hour",
                          DoubleValue(40.0),
                          MakeDoubleAccessor(&HighwayTrafficModel::m_brakeEventsPerHour),
                          MakeDoubleChecker<double>());
    return tid;
}

HighwayTrafficModel::HighwayTrafficModel()
{
    m_uniform = CreateObject<UniformRandomVariable>();
}

HighwayTrafficModel::~HighwayTrafficModel()
{
}

int64_t
HighwayTrafficModel::AssignStreams(int64_t stream)
{
    m_uniform->SetStream(stream);
    return 1;
}

void
HighwayTrafficModel::Install(const NodeContainer& nodes, double roadLength)
{
    m_roadLength = roadLength;
    for (uint32_t i = 0; i < nodes.GetN(); ++i)
    {
        Ptr<Node> n = nodes.Get(i);
        Ptr<ConstantVelocityMobilityModel> mm = n->GetObject<ConstantVelocityMobilityModel>();
        if (!mm)
        {
            continue;
        }
        Vector v = mm->GetVelocity();
        Vector p = mm->GetPosition();

        Vehicle veh;
        veh.node = n;
        veh.dynamics = CreateObject<VehicleDynamics>();
        n->AggregateObject(veh.dynamics);
        veh.speed = std::fabs(v.x);
        veh.desiredSpeed = std::max(5.0, veh.speed);
        veh.direction = v.x >= 0 ? 1 : -1;
        // Heavy vehicles accelerate and brake less sharply. Mixing classes is
        // what keeps the speed distribution wide once car following has had
        // time to equalise it, and a wide speed distribution is what keeps the
        // ETSI CAM trigger period from collapsing onto a single value.
        bool heavy = veh.desiredSpeed < 24.0;
        veh.maxAccel = heavy ? 0.7 : m_maxAccel;
        veh.comfortDecel = heavy ? 1.4 : m_comfortDecel;
        // Lane index derived from the y coordinate the scenario assigned.
        veh.lane = static_cast<int>(std::round(p.y));
        veh.brakeUntil = -1.0;
        m_vehicles.push_back(veh);
    }
    NS_LOG_INFO("HighwayTrafficModel took control of " << m_vehicles.size() << " vehicles");
}

void
HighwayTrafficModel::Start()
{
    m_running = true;
    Simulator::ScheduleNow(&HighwayTrafficModel::Step, this);
}

void
HighwayTrafficModel::Step()
{
    if (!m_running)
    {
        return;
    }
    double dt = m_step.GetSeconds();
    double now = Simulator::Now().GetSeconds();

    // Group by lane so each vehicle follows the car ahead in its own lane.
    // The key combines direction and lane; y is already signed by direction.
    std::map<int, std::vector<size_t>> byLane;
    for (size_t i = 0; i < m_vehicles.size(); ++i)
    {
        byLane[m_vehicles[i].lane].push_back(i);
    }

    for (auto& kv : byLane)
    {
        std::vector<size_t>& lane = kv.second;
        int dir = m_vehicles[lane.front()].direction;

        // Order along the direction of travel.
        std::sort(lane.begin(), lane.end(), [&](size_t a, size_t b) {
            double xa = m_vehicles[a].node->GetObject<ConstantVelocityMobilityModel>()
                            ->GetPosition().x;
            double xb = m_vehicles[b].node->GetObject<ConstantVelocityMobilityModel>()
                            ->GetPosition().x;
            return dir > 0 ? xa < xb : xa > xb;
        });

        for (size_t k = 0; k < lane.size(); ++k)
        {
            Vehicle& veh = m_vehicles[lane[k]];
            Ptr<ConstantVelocityMobilityModel> mm =
                veh.node->GetObject<ConstantVelocityMobilityModel>();
            Vector p = mm->GetPosition();

            // The leader is the next vehicle ahead, wrapping to the first.
            size_t leaderIdx = lane[(k + 1) % lane.size()];
            const Vehicle& leader = m_vehicles[leaderIdx];
            Vector lp = leader.node->GetObject<ConstantVelocityMobilityModel>()->GetPosition();

            double gap;
            if (lane.size() < 2)
            {
                gap = m_roadLength; // free road
            }
            else
            {
                gap = dir > 0 ? lp.x - p.x : p.x - lp.x;
                if (gap < 0)
                {
                    gap += m_roadLength; // the leader has wrapped around
                }
                gap -= m_vehicleLength;
            }
            gap = std::max(gap, 0.5);

            double dv = veh.speed - leader.speed;
            double sStar =
                m_minGap + std::max(0.0,
                                    veh.speed * m_desiredTimeGap +
                                        veh.speed * dv /
                                            (2.0 * std::sqrt(veh.maxAccel * veh.comfortDecel)));
            double accel = veh.maxAccel * (1.0 - std::pow(veh.speed / veh.desiredSpeed, m_delta) -
                                           (sStar / gap) * (sStar / gap));

            // Emergency braking events. These are genuine hazards, and they are
            // what makes a DENM meaningful rather than a thinned Poisson draw.
            if (now < veh.brakeUntil)
            {
                accel = -m_brakeDecel;
            }
            else
            {
                double pBrake = m_brakeEventsPerHour / 3600.0 * dt;
                if (m_uniform->GetValue(0.0, 1.0) < pBrake)
                {
                    veh.brakeUntil = now + m_brakeDuration.GetSeconds();
                    accel = -m_brakeDecel;
                }
            }

            accel = std::max(-8.0, std::min(accel, veh.maxAccel));
            veh.speed = std::max(0.0, veh.speed + accel * dt);

            veh.dynamics->SetAcceleration(accel);
            veh.dynamics->SetHardBraking(accel < -m_hardBrakeThreshold);

            mm->SetVelocity(Vector(veh.speed * dir, 0.0, 0.0));

            // Wrap the road so density and the neighbour set stay stationary.
            if (dir > 0 && p.x > m_roadLength)
            {
                p.x -= m_roadLength;
                mm->SetPosition(p);
            }
            else if (dir < 0 && p.x < 0)
            {
                p.x += m_roadLength;
                mm->SetPosition(p);
            }
        }
    }

    Simulator::Schedule(m_step, &HighwayTrafficModel::Step, this);
}

} // namespace ns3
