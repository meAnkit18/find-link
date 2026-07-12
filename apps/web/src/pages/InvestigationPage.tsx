import { useEffect, useRef, useState } from "react";
import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";

cytoscape.use(fcose);

export function riskColor(level: string): string {
  switch (level) {
    case "high":
      return "#DC2626";
    case "medium":
      return "#F59E0B";
    default:
      return "#10B981";
  }
}

interface EntityNode {
  id: string;
  label: string;
  tags: Record<string, unknown>;
}

interface EntityEdge {
  src: string;
  dst: string;
  edge_type: string;
  rank: number;
  properties: Record<string, unknown>;
}

interface GraphData {
  nodes: EntityNode[];
  edges: EntityEdge[];
}

export function InvestigationGraphPage() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [selectedNode, setSelectedNode] = useState<EntityNode | null>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<EntityNode[]>([]);
  const [riskLevel, setRiskLevel] = useState<string | null>(null);
  const [riskFactors, setRiskFactors] = useState<
    { code: string; explanation: string }[]
  >([]);

  useEffect(() => {
    if (!containerRef.current) return;
    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "background-color": "#3B82F6",
            color: "#E5E7EB",
            "text-wrap": "wrap",
            "text-max-width": 120,
            "font-size": 10,
            width: 40,
            height: 40,
          },
        },
        {
          selector: "node[risk_color]",
          style: {
            "background-color": "data(risk_color)",
          },
        },
        {
          selector: "edge",
          style: {
            width: 2,
            label: "data(label)",
            "curve-style": "bezier",
            "line-color": "#475569",
            "target-arrow-color": "#475569",
            "target-arrow-shape": "triangle",
            "font-size": 8,
            color: "#94A3B8",
          },
        },
      ],
      layout: {
        name: "fcose",
        animate: true,
        fit: true,
      },
    });

    cy.on("tap", "node", (evt) => {
      const node = evt.target;
      const data = node.data() as unknown as EntityNode;
      setSelectedNode(data);
      fetchRisk(data.id);
    });

    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        setSelectedNode(null);
      }
    });

    return () => cy.destroy();
  }, []);

  function loadGraph(data: GraphData) {
    setGraphData(data);
    const cy = (window as unknown as Record<string, unknown>).__cy as cytoscape.Core | undefined;
    if (!cy) return;
    cy.elements().remove();
    for (const node of data.nodes) {
      cy.add({
        group: "nodes",
        data: {
          id: node.id,
          label: node.label || node.id,
          ...node.tags,
        },
      });
    }
    for (const edge of data.edges) {
      cy.add({
        group: "edges",
        data: {
          id: `${edge.src}-${edge.dst}-${edge.edge_type}`,
          source: edge.src,
          target: edge.dst,
          label: edge.edge_type,
        },
      });
    }
    cy.layout({ name: "fcose", animate: true, fit: true }).run();
  }

  async function handleSearch() {
    if (!searchQuery.trim()) return;
    try {
      const res = await fetch(
        `/api/graphs/default/entities/search?q=${encodeURIComponent(searchQuery)}&entity_type=person`
      );
      const data: EntityNode[] = await res.json();
      setSearchResults(data);
    } catch {
      setSearchResults([]);
    }
  }

  async function handleSelectResult(entity: EntityNode) {
    try {
      const res = await fetch(`/api/graphs/default/entities/${entity.entity_id}/graph?depth=1`);
      const data: GraphData = await res.json();
      loadGraph(data);
      setSearchResults([]);
    } catch {
      // ignore
    }
  }

  async function fetchRisk(entityId: string) {
    try {
      const res = await fetch(`/api/graphs/default/entities/${entityId}/risk/explain`);
      const data: {
        level: string;
        factors: { code: string; explanation: string }[];
      } = await res.json();
      setRiskLevel(data.level);
      setRiskFactors(data.factors || []);
    } catch {
      setRiskLevel(null);
      setRiskFactors([]);
    }
  }

  return (
    <div className="explorer-layout">
      <div className="top-bar">
        <div className="top-bar-left">
          <h2>Investigation</h2>
        </div>
        <div className="top-bar-center">
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              type="text"
              placeholder="Search people..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              style={{
                padding: "6px 12px",
                borderRadius: 6,
                border: "1px solid #374151",
                background: "#1F2937",
                color: "#E5E7EB",
                width: 300,
              }}
            />
            <button onClick={handleSearch} className="btn btn-primary">
              Search
            </button>
          </div>
          {searchResults.length > 0 && (
            <div
              style={{
                position: "absolute",
                top: "100%",
                left: 0,
                right: 0,
                background: "#1F2937",
                border: "1px solid #374151",
                borderRadius: 6,
                zIndex: 100,
                maxHeight: 300,
                overflow: "auto",
              }}
            >
              {searchResults.map((result) => (
                <div
                  key={result.entity_id}
                  onClick={() => handleSelectResult(result)}
                  style={{
                    padding: "8px 12px",
                    cursor: "pointer",
                    borderBottom: "1px solid #374151",
                  }}
                >
                  {result.label || result.entity_id}
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="top-bar-right">
          <span className="badge badge-primary">Graph Intelligence Platform</span>
        </div>
      </div>

      <div className="explorer-body">
        <div className="explorer-left">
          <div className="panel">
            <h3>Filters</h3>
            <div className="filter-group">
              <label>Depth</label>
              <select className="select">
                <option value="1">1 hop</option>
                <option value="2">2 hops</option>
                <option value="3">3 hops</option>
              </select>
            </div>
            <div className="filter-group">
              <label>Entity Type</label>
              <div className="checkbox-list">
                <label><input type="checkbox" defaultChecked /> Person</label>
                <label><input type="checkbox" defaultChecked /> Company</label>
                <label><input type="checkbox" defaultChecked /> Address</label>
                <label><input type="checkbox" defaultChecked /> Phone</label>
                <label><input type="checkbox" defaultChecked /> Email</label>
              </div>
            </div>
            <div className="filter-group">
              <label>Risk Level</label>
              <div className="checkbox-list">
                <label><input type="checkbox" defaultChecked /> High</label>
                <label><input type="checkbox" defaultChecked /> Medium</label>
                <label><input type="checkbox" defaultChecked /> Low</label>
              </div>
            </div>
          </div>
        </div>

        <div className="explorer-center" ref={containerRef} />

        <div className="explorer-right">
          {selectedNode ? (
            <div className="panel">
              <h3>{selectedNode.label || selectedNode.id}</h3>
              <p className="text-secondary">ID: {selectedNode.id}</p>

              {riskLevel && (
                <div className="risk-section">
                  <h4>Risk Assessment</h4>
                  <div
                    className="risk-badge"
                    style={{ background: riskColor(riskLevel), color: "#fff" }}
                  >
                    {riskLevel.toUpperCase()}
                  </div>
                  {riskFactors.length > 0 && (
                    <ul className="risk-factors">
                      {riskFactors.map((f, i) => (
                        <li key={i}>{f.explanation}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              <h4>Properties</h4>
              <div className="properties-grid">
                {Object.entries(selectedNode.tags || {}).map(([key, value]) => (
                  <div key={key} className="property-row">
                    <span className="property-key">{key}</span>
                    <span className="property-value">
                      {typeof value === "object" ? JSON.stringify(value) : String(value)}
                    </span>
                  </div>
                ))}
              </div>

              <div className="btn-group">
                <button className="btn btn-primary btn-sm">Expand</button>
                <button className="btn btn-secondary btn-sm">Shortest Path</button>
              </div>
            </div>
          ) : (
            <div className="panel">
              <h3>Investigation Tools</h3>
              <p className="text-secondary">
                Select a node to view details, risk assessment, and evidence.
              </p>
              <div className="tool-list">
                <div className="tool-item">
                  <strong>Search</strong>
                  <p>Find people, companies, and entities</p>
                </div>
                <div className="tool-item">
                  <strong>Expand</strong>
                  <p>Explore connections through graph traversal</p>
                </div>
                <div className="tool-item">
                  <strong>Risk</strong>
                  <p>Calculate direct and indirect risk scores</p>
                </div>
                <div className="tool-item">
                  <strong>Path</strong>
                  <p>Find shortest paths between entities</p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="bottom-tray">
        <div className="tray-tabs">
          <button className="tray-tab active">Notes</button>
          <button className="tray-tab">Path Analysis</button>
          <button className="tray-tab">Suspicious Patterns</button>
          <button className="tray-tab">Evidence</button>
        </div>
        <div className="tray-content">
          <p className="text-secondary">
            Use the graph canvas to explore entities. Select a node to see its
            properties and risk assessment.
          </p>
        </div>
      </div>
    </div>
  );
}
