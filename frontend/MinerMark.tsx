import Image from "next/image";

import miningAnimation from "./assets/mining-animation.gif";
import slaiMinerMark from "./assets/slaiminer-mark.png";

type Props = {
  isMining: boolean;
  priority?: boolean;
};

export function MinerMark({ isMining, priority = false }: Props) {
  return (
    <Image
      src={isMining ? miningAnimation : slaiMinerMark}
      alt="SLAI Miner"
      priority={priority}
      unoptimized={isMining}
    />
  );
}
