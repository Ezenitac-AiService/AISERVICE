import React, { useState } from 'react';

// --- SVG 방사형 차트 컴포넌트 ---
export const RadarChart = ({ data, selectedAttributeName, onSelectAttribute }) => {
  if (!data || data.length === 0) {
    return <div style={{ textAlign: 'center', color: '#888', padding: '60px 0' }}>등록된 속성 분석 데이터가 없습니다.</div>;
  }

  const uniqueData = [];
  const seenNames = new Set();
  data.forEach(item => {
    if (item.attribute_name && !seenNames.has(item.attribute_name)) {
      seenNames.add(item.attribute_name);
      uniqueData.push(item);
    }
  });

  const [showPos, setShowPos] = useState(true);
  const [showNeg, setShowNeg] = useState(true);
  const [showNeu, setShowNeu] = useState(true);

  const size = 425;
  const center = size / 2;
  const radius = 135;
  const total = uniqueData.length;

  const getCoordinates = (index, valueRatio) => {
    const angle = (Math.PI * 2 / total) * index - Math.PI / 2;
    const x = center + radius * valueRatio * Math.cos(angle);
    const y = center + radius * valueRatio * Math.sin(angle);
    return { x, y };
  };

  const levels = [0.2, 0.4, 0.6, 0.8, 1.0];
  const gridPolygons = levels.map(level => {
    return uniqueData.map((_, i) => {
      const { x, y } = getCoordinates(i, level);
      return `${x},${y}`;
    }).join(' ');
  });

  const positivePoints = uniqueData.map((d, i) => {
    const score = Math.max(15, Math.min(100, d.score || 50));
    return getCoordinates(i, score / 100);
  });
  const positivePolygon = positivePoints.map(p => `${p.x},${p.y}`).join(' ');

  const negativePoints = uniqueData.map((d, i) => {
    const totalCount = d.total_count || 0;
    const negRatio = totalCount > 0 ? ((d.neg_count || 0) / totalCount) * 100 : 0;
    const score = Math.max(0, Math.min(100, negRatio));
    return getCoordinates(i, score / 100);
  });
  const negativePolygon = negativePoints.map(p => `${p.x},${p.y}`).join(' ');

  const neutralPoints = uniqueData.map((d, i) => {
    const totalCount = d.total_count || 0;
    const neuRatio = totalCount > 0 ? ((d.neu_count || 0) / totalCount) * 100 : 0;
    const score = Math.max(0, Math.min(100, neuRatio));
    return getCoordinates(i, score / 100);
  });
  const neutralPolygon = neutralPoints.map(p => `${p.x},${p.y}`).join(' ');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '15px', width: '100%' }}>
      <style>
        {`
          @keyframes radarEntrance {
            0% { transform: scale(0.85); opacity: 0; }
            100% { transform: scale(1); opacity: 1; }
          }
          .animated-radar {
            animation: radarEntrance 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
            transform-origin: center;
          }
          .legend-btn {
            transition: all 0.2s ease;
            cursor: pointer;
            user-select: none;
          }
          .legend-btn:hover {
            transform: translateY(-1px);
            opacity: 0.85 !important;
          }
        `}
      </style>

      {/* 감성 필터 토글 버튼 영역 */}
      <div style={{ display: 'flex', width: '100%', justifyContent: 'flex-start', paddingLeft: '20px', gap: '12px', alignItems: 'center' }}>
        <span style={{ fontSize: '0.85rem', fontWeight: 'bold', color: '#333', marginRight: '4px' }}>감성 필터:</span>
        
        <div 
          onClick={(e) => { e.preventDefault(); setShowPos(!showPos); }}
          className="legend-btn"
          style={{ 
            display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem', fontWeight: 'bold', 
            color: showPos ? '#1d4ed8' : '#9ca3af', backgroundColor: showPos ? '#eff6ff' : '#f3f4f6', 
            padding: '4px 10px', borderRadius: '15px', border: showPos ? '1px solid #bfdbfe' : '1px solid #e5e7eb',
            opacity: showPos ? 1 : 0.6 
          }}
        >
          <span style={{ width: '8px', height: '8px', backgroundColor: showPos ? '#3b82f6' : '#9ca3af', borderRadius: '50%' }}></span>
          긍정 {showPos ? 'ON' : 'OFF'}
        </div>

        <div 
          onClick={(e) => { e.preventDefault(); setShowNeg(!showNeg); }}
          className="legend-btn"
          style={{ 
            display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem', fontWeight: 'bold', 
            color: showNeg ? '#dc2626' : '#9ca3af', backgroundColor: showNeg ? '#fef2f2' : '#f3f4f6', 
            padding: '4px 10px', borderRadius: '15px', border: showNeg ? '1px solid #fecaca' : '1px solid #e5e7eb',
            opacity: showNeg ? 1 : 0.6 
          }}
        >
          <span style={{ width: '8px', height: '8px', backgroundColor: showNeg ? '#ef4444' : '#9ca3af', borderRadius: '50%' }}></span>
          부정 {showNeg ? 'ON' : 'OFF'}
        </div>

        <div 
          onClick={(e) => { e.preventDefault(); setShowNeu(!showNeu); }}
          className="legend-btn"
          style={{ 
            display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem', fontWeight: 'bold', 
            color: showNeu ? '#4b5563' : '#9ca3af', backgroundColor: showNeu ? '#f3f4f6' : '#f3f4f6', 
            padding: '4px 10px', borderRadius: '15px', border: showNeu ? '1px solid #d1d5db' : '1px solid #e5e7eb',
            opacity: showNeu ? 1 : 0.6 
          }}
        >
          <span style={{ width: '8px', height: '8px', backgroundColor: showNeu ? '#9ca3af' : '#d1d5db', borderRadius: '50%' }}></span>
          중립 {showNeu ? 'ON' : 'OFF'}
        </div>
      </div>

      <svg width={size} height={size} className="animated-radar" style={{ overflow: 'visible' }}>
        {gridPolygons.map((points, idx) => (
          <polygon
            key={`grid-${idx}`}
            points={points}
            fill="none"
            stroke="#e2e8f0"
            strokeWidth="1.5"
            strokeDasharray={idx === levels.length - 1 ? 'none' : '2,2'}
          />
        ))}

        {uniqueData.map((_, i) => {
          const { x, y } = getCoordinates(i, 1.0);
          return <line key={`line-${i}`} x1={center} y1={center} x2={x} y2={y} stroke="#cbd5e1" strokeWidth="1" />;
        })}

        {showNeu && (
          <polygon
            points={neutralPolygon}
            fill="rgba(156, 163, 175, 0.12)"
            stroke="#9ca3af"
            strokeWidth="1.5"
            style={{ transition: 'opacity 0.3s ease', opacity: showNeu ? 1 : 0 }}
          />
        )}

        {showNeg && (
          <polygon
            points={negativePolygon}
            fill="rgba(239, 68, 68, 0.15)"
            stroke="#ef4444"
            strokeWidth="2"
            style={{ transition: 'opacity 0.3s ease', opacity: showNeg ? 1 : 0 }}
          />
        )}

        {showPos && (
          <polygon
            points={positivePolygon}
            fill="rgba(59, 130, 246, 0.25)"
            stroke="#2563eb"
            strokeWidth="2.5"
            style={{ transition: 'opacity 0.3s ease', opacity: showPos ? 1 : 0 }}
          />
        )}

        {uniqueData.map((d, i) => {
          const outerPoint = getCoordinates(i, 1.32); 
          const isSelected = selectedAttributeName === d.attribute_name; 
          const negCount = d.neg_count || 0;
          const neuCount = d.neu_count || 0;

          return (
            <g 
              key={`vertex-${d.attribute_name}-${i}`} 
              style={{ cursor: 'pointer' }}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onSelectAttribute(d.attribute_name); 
              }}
            >
              <circle cx={outerPoint.x} cy={outerPoint.y} r="35" fill="transparent" />
              
              <text
                x={outerPoint.x}
                y={outerPoint.y}
                textAnchor="middle"
                style={{ pointerEvents: 'none', userSelect: 'none' }} 
              >
                <tspan 
                  x={outerPoint.x} 
                  dy="-0.4em"
                  fontSize={isSelected ? '14px' : '12px'}
                  fontWeight={isSelected ? 'bold' : '600'}
                  fill={isSelected ? '#1d4ed8' : '#475569'}
                >
                  {d.attribute_name}
                </tspan>
                <tspan 
                  x={outerPoint.x} 
                  dy="1.3em"
                  fontSize={isSelected ? '12px' : '11px'}
                  fontWeight="normal"
                  fill={isSelected ? '#3b82f6' : '#64748b'}
                >
                  (긍정 {d.pos_count} / 부정 {negCount} / 중립 {neuCount})
                </tspan>
              </text>
            </g>
          );
        })}
      </svg>

      {/* 하단 속성별 총 건수 태그 리스트 */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', justifyContent: 'center', marginTop: '15px', maxWidth: '450px' }}>
        {uniqueData.map((attr, i) => {
          const isSelected = selectedAttributeName === attr.attribute_name;

          return (
            <span
              key={`tag-${attr.attribute_name}-${i}`}
              onClick={(e) => {
                e.preventDefault();
                onSelectAttribute(attr.attribute_name);
              }}
              style={{
                fontSize: '0.85rem',
                padding: '5px 12px',
                borderRadius: '8px',
                backgroundColor: isSelected ? '#eff6ff' : '#f8fafc',
                color: isSelected ? '#1d4ed8' : '#334155',
                border: isSelected ? '1px solid #93c5fd' : '1px solid #e2e8f0',
                fontWeight: isSelected ? 'bold' : '500',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                boxShadow: '0 1px 2px rgba(0,0,0,0.02)'
              }}
            >
              {attr.attribute_name} <strong style={{ color: isSelected ? '#2563eb' : '#0f172a' }}>{attr.total_count}건</strong>
            </span>
          );
        })}
      </div>

      <div style={{ 
        fontSize: '0.8rem', color: '#4b5563', backgroundColor: '#f8fafc', border: '1px solid #e2e8f0',
        borderRadius: '8px', textAlign: 'center', marginTop: '8px', wordBreak: 'keep-all', lineHeight: '1.4', padding: '10px 16px',
        maxWidth: '460px', boxShadow: '0 1px 2px rgba(0,0,0,0.02)'
      }}>
        💡 <span style={{ fontWeight: '500' }}>안내 :</span> 중립 리뷰 데이터는 감성 분석 보고서 요약 대상에서 제외되었습니다.
      </div>
    </div>
  );
};

// --- SVG 원형 파이 차트 컴포넌트 ---
export const SentimentPieChart = ({ stats, sentimentTab, onSelectTab }) => {
  const total = stats.total_sentence_count || 0;
  const positive = stats.positive_count || 0;
  const negative = stats.negative_count || 0;
  const neutral = stats.neutral_count || (total - positive - negative);

  if (total === 0) {
    return <div style={{ textAlign: 'center', color: '#888', padding: '60px 0' }}>등록된 분석 데이터가 없습니다.</div>;
  }

  const posRatio = positive / total;
  const negRatio = negative / total;
  const neuRatio = neutral / total;

  const size = 340;
  const center = size / 2;
  const radius = 125;

  const getCoordinatesForPercent = (percent) => {
    const x = center + radius * Math.cos(2 * Math.PI * percent);
    const y = center + radius * Math.sin(2 * Math.PI * percent);
    return [x, y];
  };

  let cumulativePercent = 0;
  const slices = [
    { label: 'positive', count: positive, color: '#3b82f6', percent: posRatio },
    { label: 'negative', count: negative, color: '#ef4444', percent: negRatio },
    { label: 'neutral', count: neutral, color: '#9ca3af', percent: neuRatio }
  ].filter(s => s.percent > 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '20px', width: '100%', justifyContent: 'center' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {slices.map((slice, i) => {
          const startPercent = cumulativePercent;
          cumulativePercent += slice.percent;
          const endPercent = cumulativePercent;

          const [startX, startY] = getCoordinatesForPercent(startPercent);
          const [endX, endY] = getCoordinatesForPercent(endPercent);
          const largeArcFlag = slice.percent > 0.5 ? 1 : 0;
          const pathData = `M ${center} ${center} L ${startX} ${startY} A ${radius} ${radius} 0 ${largeArcFlag} 1 ${endX} ${endY} Z`;

          const isSelected = sentimentTab === slice.label;

          return (
            <path
              key={`slice-${i}`}
              d={pathData}
              fill={slice.color}
              stroke="#fff"
              strokeWidth="2.5"
              style={{ cursor: 'pointer', opacity: isSelected ? 1 : 0.75, transition: 'opacity 0.2s' }}
              onClick={(e) => { e.preventDefault(); onSelectTab(slice.label); }}
            />
          );
        })}
      </svg>
      <div style={{ display: 'flex', gap: '20px', fontSize: '0.95rem', color: '#555' }}>
        <span style={{ cursor: 'pointer', fontWeight: sentimentTab === 'positive' ? 'bold' : 'normal', color: sentimentTab === 'positive' ? '#1d4ed8' : '#555' }} onClick={(e) => { e.preventDefault(); onSelectTab('positive'); }}>🔵 긍정 {positive}건 ({stats.positive_ratio}%)</span>
        <span style={{ cursor: 'pointer', fontWeight: sentimentTab === 'negative' ? 'bold' : 'normal', color: sentimentTab === 'negative' ? '#1d4ed8' : '#555' }} onClick={(e) => { e.preventDefault(); onSelectTab('negative'); }}>🔴 부정 {negative}건 ({stats.negative_ratio}%)</span>
        <span style={{ cursor: 'pointer', fontWeight: sentimentTab === 'neutral' ? 'bold' : 'normal', color: sentimentTab === 'neutral' ? '#1d4ed8' : '#555' }} onClick={(e) => { e.preventDefault(); onSelectTab('neutral'); }}>⚪ 중립 {neutral}건</span>
      </div>

      <div style={{ 
        fontSize: '0.8rem', color: '#4b5563', backgroundColor: '#f8fafc', border: '1px solid #e2e8f0',
        borderRadius: '8px', textAlign: 'center', marginTop: '8px', wordBreak: 'keep-all', lineHeight: '1.4', padding: '10px 16px',
        maxWidth: '460px', boxShadow: '0 1px 2px rgba(0,0,0,0.02)'
      }}>
        💡 <span style={{ fontWeight: '500' }}>안내 :</span> 중립 리뷰 데이터는 분석요약 보고서 작성 대상에서 제외되었습니다.
      </div>
    </div>
  );
};

// --- 리뷰 텍스트 하이라이팅 컴포넌트 함수 (속성 이름 라벨 배지 표기 추가) ---
// ProductComponents.jsx 맨 아래 함수 수정

export const renderHighlightedReviewText = (fullText, sentences) => {
  if (!fullText) return null;
  if (!sentences || sentences.length === 0) return fullText;

  let matches = [];
  sentences.forEach(s => {
    const textToFind = s.separated_sentence;
    if (!textToFind) return;

    // 1. 단순 exact match 시도
    let idx = fullText.indexOf(textToFind);
    if (idx !== -1) {
      while (idx !== -1) {
        matches.push({
          start: idx,
          end: idx + textToFind.length,
          sentiment: s.sentiment_label,
          attributeName: s.attribute_name || s.display_name
        });
        idx = fullText.indexOf(textToFind, idx + 1);
      }
    } else {
      // 2. 물결표(~) 등의 특수문자 차이 흡수를 위한 유연한 정규식 검색
      try {
        const escaped = textToFind.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        // 분석 문장의 각 글자 사이에 물결표(~)나 공백이 들어갈 수 있도록 허용
        const pattern = escaped.split('').join('~*\\s*');
        const regex = new RegExp(pattern, 'g');
        let match;
        while ((match = regex.exec(fullText)) !== null) {
          matches.push({
            start: match.index,
            end: match.index + match[0].length,
            sentiment: s.sentiment_label,
            attributeName: s.attribute_name || s.display_name
          });
        }
      } catch (e) {
        console.error('Highlight regex error:', e);
      }
    }
  });

  if (matches.length === 0) return fullText;

  matches.sort((a, b) => a.start - b.start);

  let nonOverlapping = [];
  let lastEnd = 0;
  for (let m of matches) {
    if (m.start >= lastEnd) {
      nonOverlapping.push(m);
      lastEnd = m.end;
    } else if (m.end > lastEnd) {
      m.start = lastEnd;
      if (m.start < m.end) {
        nonOverlapping.push(m);
        lastEnd = m.end;
      }
    }
  }

  let resultNodes = [];
  let currentIndex = 0;

  nonOverlapping.forEach((m, idx) => {
    if (m.start > currentIndex) {
      resultNodes.push(fullText.substring(currentIndex, m.start));
    }
    const matchedText = fullText.substring(m.start, m.end);
    let bg = '#fef08a';
    let color = '#854d0e';
    if (m.sentiment === 'positive') {
      bg = '#dbeafe'; 
      color = '#1e40af';
    } else if (m.sentiment === 'negative') {
      bg = '#fee2e2'; 
      color = '#991b1b';
    } else if (m.sentiment === 'neutral') {
      bg = '#f3f4f6'; 
      color = '#374151';
    }

    resultNodes.push(
      <span 
        key={`hl-${idx}`} 
        style={{ 
          backgroundColor: bg, 
          color: color, 
          padding: '2px 6px', 
          borderRadius: '4px', 
          fontWeight: '500',
          marginRight: '4px',
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px'
        }}
      >
        {m.attributeName && (
          <span style={{
            fontSize: '0.75rem',
            fontWeight: 'bold',
            padding: '1px 4px',
            backgroundColor: 'rgba(255, 255, 255, 0.7)',
            borderRadius: '3px',
            border: '1px solid currentColor'
          }}>
            {m.attributeName}
          </span>
        )}
        {matchedText}
      </span>
    );
    currentIndex = m.end;
  });

  if (currentIndex < fullText.length) {
    resultNodes.push(fullText.substring(currentIndex));
  }

  return resultNodes;
};