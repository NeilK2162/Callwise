import Link from "next/link";
import { LayoutDashboard, PhoneOutgoing, Settings } from "lucide-react";
import { EqSmall } from "@/components/BrandMark";

export function SidebarRail() {
  return (
    <aside className="rail">
      <Link href="/" className="rail-brand" title="Callwise home">
        <EqSmall />
      </Link>
      <nav className="rail-nav" aria-label="Dashboard navigation">
        <Link href="/dashboard" className="rail-btn on" title="Feed">
          <LayoutDashboard size={20} strokeWidth={2} />
        </Link>
        <button type="button" className="rail-btn" title="Outbound (use Start Outbound Call)" disabled>
          <PhoneOutgoing size={20} strokeWidth={2} />
        </button>
      </nav>
      <div className="rail-foot">
        <button type="button" className="rail-btn" title="Settings (coming soon)" disabled>
          <Settings size={20} strokeWidth={2} />
        </button>
      </div>
    </aside>
  );
}
