#include "cv2x-trace-store.h"

#include "ns3/abort.h"
#include "ns3/log.h"

#include <sys/stat.h>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("Cv2xTraceStore");

Cv2xTraceStore&
Cv2xTraceStore::Get()
{
    static Cv2xTraceStore instance;
    return instance;
}

Cv2xTraceStore::~Cv2xTraceStore()
{
    CloseAll();
}

void
Cv2xTraceStore::Configure(const std::string& outputDir, const std::string& runTag)
{
    NS_ABORT_MSG_IF(!m_tables.empty(), "Configure() must precede any Open()");
    m_outputDir = outputDir;
    m_runTag = runTag;
    mkdir(m_outputDir.c_str(), 0755);
}

void
Cv2xTraceStore::Open(const std::string& table, const std::string& headerRow)
{
    if (m_tables.find(table) != m_tables.end())
    {
        return;
    }
    auto t = std::make_unique<Table>();
    std::string path = m_outputDir + "/" + table + "_" + m_runTag + ".csv";
    t->stream.open(path, std::ios::out | std::ios::trunc);
    NS_ABORT_MSG_IF(!t->stream.is_open(), "Cannot open trace file " << path);
    t->stream << headerRow << "\n";
    m_tables[table] = std::move(t);
    NS_LOG_INFO("Opened trace table " << path);
}

void
Cv2xTraceStore::Write(const std::string& table, const std::string& row)
{
    auto it = m_tables.find(table);
    NS_ABORT_MSG_IF(it == m_tables.end(), "Write to unopened table " << table);
    it->second->stream << row << "\n";
    it->second->rows++;
}

uint64_t
Cv2xTraceStore::Rows(const std::string& table) const
{
    auto it = m_tables.find(table);
    return it == m_tables.end() ? 0 : it->second->rows;
}

void
Cv2xTraceStore::FlushAll()
{
    for (auto& kv : m_tables)
    {
        if (kv.second->stream.is_open())
        {
            kv.second->stream.flush();
        }
    }
}

void
Cv2xTraceStore::CloseAll()
{
    for (auto& kv : m_tables)
    {
        if (kv.second->stream.is_open())
        {
            kv.second->stream.flush();
            kv.second->stream.close();
        }
    }
    m_tables.clear();
}

} // namespace ns3
