import Image from "next/image";

import remyMark from "./assets/slaiminer-mark.png";

const footerLinks = [
  { label: "TaoStats SN67", href: "https://taostats.io/subnets/67/statistics" },
  { label: "TaoMarketCap SN67", href: "https://taomarketcap.com/subnets/67" },
  { label: "Harnyx", href: "https://harnyx.ai/" },
  { label: "Harnyx GitHub", href: "https://github.com/harnyx/harnyx" },
  { label: "Bittensor Docs", href: "https://docs.bittensor.com/" },
] as const;

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="site-footer__top">
        <div className="footer-brand">
          <Image src={remyMark} alt="" />
          <div>
            <strong>SLAI Miner SN67</strong>
            <span>Harnyx research-miner engineering dashboard</span>
          </div>
        </div>

        <div className="footer-column">
          <p>Network &amp; research</p>
          {footerLinks.map((link) => (
            <a key={link.href} href={link.href} target="_blank" rel="noreferrer">
              <span>{link.label}</span>
              <span aria-hidden="true">↗</span>
            </a>
          ))}
        </div>
      </div>

      <div className="site-footer__bottom">
        <p>© {new Date().getFullYear()} Remy3Design</p>
        <p className="footer-note">
          Read-only observability. No wallet management, subnet registration, TAO transfer, or artifact submission controls.
        </p>
      </div>
    </footer>
  );
}
