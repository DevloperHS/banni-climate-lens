import { useApp } from "../state/AppState";

export default function Methodology() {
  const { theme } = useApp();

  return (
    <iframe
      title="Methodology"
      src={`/methodology/index.html?theme=${theme}`}
      className="block h-screen w-full border-0"
    />
  );
}
