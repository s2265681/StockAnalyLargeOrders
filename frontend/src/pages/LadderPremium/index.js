import React from 'react';
import LadderGantt from '../EmotionCycle/LadderGantt';
import './index.css';

function LadderPremium({ preview = false }) {
  return (
    <div className="ladder-premium-page">
      <div className="ladder-premium-card">
        <LadderGantt preview={preview} />
      </div>
    </div>
  );
}

export default LadderPremium;
