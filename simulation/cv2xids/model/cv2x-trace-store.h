/*
 * CV2X-IDS: buffered CSV trace store.
 *
 * One file per table. Tables are written flat and joined offline by the
 * feature pipeline. Keeping the receive-side tables physically separate from
 * the transmit-side truth table is deliberate: the feature extractor is
 * pointed at the receive-side files only.
 */
#ifndef CV2X_TRACE_STORE_H
#define CV2X_TRACE_STORE_H

#include <fstream>
#include <map>
#include <memory>
#include <string>

namespace ns3
{

/**
 * \brief Process-wide collection of buffered CSV output tables.
 */
class Cv2xTraceStore
{
  public:
    static Cv2xTraceStore& Get();

    /// Set the output directory and run tag. Must be called before Open().
    void Configure(const std::string& outputDir, const std::string& runTag);

    /// Open a table and write its header row. Safe to call once per table.
    void Open(const std::string& table, const std::string& headerRow);

    /// Append one already-formatted row (no trailing newline).
    void Write(const std::string& table, const std::string& row);

    /// Number of rows written to a table so far.
    uint64_t Rows(const std::string& table) const;

    /// Flush every open table without closing it. Scheduled periodically so a
    /// run that is interrupted still leaves consistent, usable tables.
    void FlushAll();

    /// Flush and close everything. Call at the end of the run.
    void CloseAll();

  private:
    Cv2xTraceStore() = default;
    ~Cv2xTraceStore();
    Cv2xTraceStore(const Cv2xTraceStore&) = delete;
    Cv2xTraceStore& operator=(const Cv2xTraceStore&) = delete;

    struct Table
    {
        std::ofstream stream;
        uint64_t rows{0};
    };

    std::string m_outputDir{"."};
    std::string m_runTag{"run"};
    std::map<std::string, std::unique_ptr<Table>> m_tables;
};

} // namespace ns3

#endif /* CV2X_TRACE_STORE_H */
