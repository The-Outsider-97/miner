import DashboardApp from "../app";
import { TaoProvider } from "../TaoContext";

export default function HomePage() {
  return (
    <TaoProvider>
      <DashboardApp />
    </TaoProvider>
  );
}
