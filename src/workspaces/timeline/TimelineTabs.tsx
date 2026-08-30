import React from 'react';
import { useTimeline } from './TimelineContext';
import './TimelineTabs.css';

 
export default function TimelineTabs() {
  const { state, dispatch } = useTimeline();
  const { compTabStack, activeCompId } = state;

  if (compTabStack.length <= 1 && activeCompId === null) {
    // Only root 
    return null;
  }

  return (
    <div className="tl-tabs">
      {compTabStack.map((tab) => {
        const isActive = tab.compId === activeCompId;
        const isRoot   = tab.compId === null;
        return (
          <div
            key={tab.compId ?? '__root__'}
            className={`tl-tabs__tab${isActive ? ' tl-tabs__tab--active' : ''}${isRoot ? ' tl-tabs__tab--root' : ''}`}
            onClick={() => dispatch({ type: 'SWITCH_COMP_TAB', compId: tab.compId })}
            title={tab.name}
          >
            <span className="tl-tabs__icon">{isRoot ? '◈' : '⊞'}</span>
            <span className="tl-tabs__name">{tab.name}</span>
            {!isRoot && (
              <button
                className="tl-tabs__close"
                title="Close tab"
                onClick={e => {
                  e.stopPropagation();
                  dispatch({ type: 'CLOSE_COMP_TAB', compId: tab.compId! });
                }}
              >✕</button>
            )}
          </div>
        );
      })}
    </div>
  );
}
