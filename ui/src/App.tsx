import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./components/Dashboard";
import RunView from "./components/RunView";
import AgentStream from "./components/AgentStream";

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/runs/:runId" element={<RunView />} />
        <Route path="/runs/:runId/agents/:agentId" element={<AgentStream />} />
      </Routes>
    </Layout>
  );
}

export default App;
