import Image from "next/image";

import harnyxMark from "./assets/harnyx-mark.png";

type Props = {
  label?: string;
};

export function Loading({ label = "Loading Miner data" }: Props) {
  return (
    <div className="route-loader" role="status" aria-live="polite">
      <div className="route-loader__orb" aria-hidden="true">
        <span />
        <span />
        <Image src={harnyxMark} alt="" priority />
      </div>
      <p>{label}</p>
    </div>
  );
}
