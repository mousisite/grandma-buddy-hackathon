import { Composition } from "remotion";
import { RoseIntro, roseIntroFrames } from "./RoseIntro";
import { FPS, HEIGHT, WIDTH } from "./theme";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="RoseIntro"
      component={RoseIntro}
      durationInFrames={roseIntroFrames()}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
    />
  );
};
