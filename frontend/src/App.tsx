import { useCallback, useRef, useState } from "react";
import { Evt, useEventStream } from "./api";
import {
  AgentTimeline, BaselineCompare, BgFx, DataExplorer, Funnel, Header, LearningPanel,
  LiveFeed, MetricsRow, NotificationCenter, QueuePanel,
} from "./components";

export default function App() {
  const [events, setEvents] = useState<Evt[]>([]);
  const buf = useRef<Evt[]>([]);
  const onEvent = useCallback((e: Evt) => {
    buf.current = [e, ...buf.current].slice(0, 300);
    setEvents(buf.current);
  }, []);
  const connected = useEventStream(onEvent);

  return (
    <>
      <BgFx />
      <div className="wrap">
        <Header connected={connected} />
        <MetricsRow />

        <div className="grid cols-2" style={{ marginTop: 18 }}>
          <LiveFeed events={events} />
          <AgentTimeline events={events} />
        </div>

        <div className="grid cols-3" style={{ marginTop: 18 }}>
          <Funnel />
          <LearningPanel />
          <QueuePanel />
        </div>

        <div style={{ marginTop: 18 }}>
          <BaselineCompare />
        </div>

        <div className="grid cols-2" style={{ marginTop: 18 }}>
          <NotificationCenter />
          <DataExplorer />
        </div>
      </div>
    </>
  );
}
