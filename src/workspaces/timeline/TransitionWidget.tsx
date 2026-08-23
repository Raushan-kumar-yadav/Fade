import React, { memo } from 'react';
import { type TransitionInfo } from '../../api/toolsApi';
import { useSelection } from '../../context/selectionContext';

interface Props {
  transition: TransitionInfo;
  trackId: string;
  zoomX: number;
  centerFrame: number;
}

const TransitionWidget = memo(function TransitionWidget({ transition, trackId, zoomX, centerFrame }: Props) {
  const { selected, setSelected } = useSelection();

  // Width of transition  
  const width = transition.duration * zoomX;
  const half = width / 2;
  const left = centerFrame * zoomX - half;

  const isSelected = selected?.type === 'transition' && selected.id === transition.transId;

  const onClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setSelected({
      type: 'transition',
      id: transition.transId,
      trackId,
      data: transition,
    });
  };

  return (
    <div
      onClick={onClick}
      title={`Transition: ${transition.typeId} (${transition.duration}f)`}
      style={{
        position: 'absolute',
        top: '25%',
        height: '50%',
        left,
        width,
        borderRadius: 4,
        background: isSelected ? 'rgba(112, 112, 255, 0.7)' : 'rgba(160, 112, 255, 0.6)',
        border: isSelected ? '1px solid #c0c0ff' : '1px solid rgba(255, 255, 255, 0.2)',
        cursor: 'pointer',
        zIndex: 50, // above clips
        boxSizing: 'border-box',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
      }}
    >
      <div style={{
        width: 14, height: 14,
        background: 'rgba(0,0,0,0.3)',
        borderRadius: 2,
        clipPath: 'polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)',
      }} />
    </div>
  );
});

export default TransitionWidget;
