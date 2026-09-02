import React, { useState, useEffect } from 'react';
import { RadarChart, SentimentPieChart, renderHighlightedReviewText } from './ProductComponents';

const BaseProductDetail = ({ productId, onBack, apiBaseUrl }) => {
  const [activeMenu, setActiveMenu] = useState('maintainProduct');
  const [subTab, setSubTab] = useState('maintain'); // 'maintain' (긍정), 'improve' (부정), 'neutral' (중립)
  const [sentimentTab, setSentimentTab] = useState('positive'); // 'positive', 'negative', 'neutral', 'all'
  
  const [reviewSort, setReviewSort] = useState('all'); 
  const [selectedAttributeFilter, setSelectedAttributeFilter] = useState('all');
  const [detailedReviews, setDetailedReviews] = useState([]);

  const [productData, setProductData] = useState(null);
  const [options, setOptions] = useState([]);
  
  const [radarData, setRadarData] = useState([]);
  const [selectedAttributeName, setSelectedAttributeName] = useState(null);
  const [overallStats, setOverallStats] = useState({});
  const [overallReport, setOverallReport] = useState({});
  const [reviewsData, setReviewsData] = useState([]);
  
  const [showSentimentSentence, setShowSentimentSentence] = useState(true);
  const [showFullReview, setShowFullReview] = useState(true);

  const [loading, setLoading] = useState(true);

  const baseUrl = apiBaseUrl || '/bteam/oliview';

  useEffect(() => {
    if (productId) {
      fetch(`${baseUrl}/api/products/${productId}`)
        .then(res => res.json())
        .then(data => {
          if (data.success) {
            setProductData(data.product);
            setOptions(data.options);
          }
          setLoading(false);
        })
        .catch(err => {
          console.error('상품 상세 정보 불러오기 실패:', err);
          setLoading(false);
        });
    }
  }, [productId, baseUrl]);

  useEffect(() => {
    if (productId) {
      let url = '';
      if (activeMenu === 'maintainProduct') {
        let attrParam = selectedAttributeName ? `&attribute_name=${encodeURIComponent(selectedAttributeName)}` : '';
        url = `${baseUrl}/api/products/${productId}/analysis-report?tab=${subTab}${attrParam}`;
      } else if (activeMenu === 'sentiment') {
        url = `${baseUrl}/api/products/${productId}/analysis-report?sentiment=${sentimentTab}`;
      }
      
      if (activeMenu !== 'reviews') {
        fetch(url)
          .then(res => res.json())
          .then(data => {
            if (data.success) {
              setRadarData(data.radar_data || []);
              setOverallStats(data.overall_stats || {});
              setOverallReport(data.overall_report || {});
              setReviewsData(data.reviews_data || []);

              if (activeMenu === 'maintainProduct' && !selectedAttributeName && data.radar_data && data.radar_data.length > 0) {
                setSelectedAttributeName(data.radar_data[0].attribute_name);
              }
            }
          })
          .catch(err => {
            console.error('분석 리포트 불러오기 실패:', err);
          });
      }
    }
  }, [productId, selectedAttributeName, subTab, sentimentTab, activeMenu, baseUrl]);

  useEffect(() => {
    if (activeMenu === 'reviews' && productId) {
      let attrQuery = selectedAttributeFilter !== 'all' ? `&attribute_name=${encodeURIComponent(selectedAttributeFilter)}` : '';
      fetch(`${baseUrl}/api/products/${productId}/reviews-detail?sort=${reviewSort}${attrQuery}`)
        .then(res => res.json())
        .then(data => {
          if (data.success) {
            setDetailedReviews(data.reviews || []);
            if (radarData.length === 0 && data.radar_data) {
              setRadarData(data.radar_data);
            }
          }
        })
        .catch(err => {
          console.error('리뷰 상세 불러오기 실패:', err);
        });
    }
  }, [activeMenu, productId, reviewSort, selectedAttributeFilter, radarData.length, baseUrl]);

  useEffect(() => {
    if (productId && radarData.length === 0) {
      fetch(`${baseUrl}/api/products/${productId}/analysis-report?tab=maintain`)
        .then(res => res.json())
        .then(data => {
          if (data.success && data.radar_data) {
            setRadarData(data.radar_data);
          }
        })
        .catch(err => {});
    }
  }, [productId, radarData.length, baseUrl]);

  const currentAttributeReport = radarData.find(item => item.attribute_name === selectedAttributeName) || {};
  
  const currentSummary = subTab === 'maintain' 
    ? (currentAttributeReport.positive_summary || '해당 속성에 대한 감성 분석 보고서가 없습니다.')
    : subTab === 'improve'
    ? (currentAttributeReport.negative_summary || '해당 속성에 대한 감성 분석 보고서가 없습니다.')
    : '중립 분석 데이터가 없습니다.';

  const currentOverallSummary = sentimentTab === 'positive' 
    ? (overallReport.keep_summary || '등록된 유지할 점 분석 보고서가 없습니다.')
    : sentimentTab === 'negative'
    ? (overallReport.improvement_summary || '등록된 개선점 분석 보고서가 없습니다.')
    : sentimentTab === 'neutral'
    ? '중립 분석 데이터가 없습니다.'
    : (overallReport.overall_summary || '등록된 전체 종합 요약 내용이 없습니다.');

  const renderFormattedSummary = (text) => {
    if (!text) return null;
    const sentences = text.split(/(?<=[.?!])\s+/).filter(s => s.trim().length > 0);
    
    if (sentences.length <= 1) {
      return text;
    }

    return sentences.map((sentence, idx) => (
      <p key={`summary-sent-${idx}`} style={{ margin: idx === sentences.length - 1 ? '0' : '0 0 8px 0', lineHeight: '1.6' }}>
        {sentence}
      </p>
    ));
  };

  const renderMaintainProduct = () => (
    <div>
      <div style={{ display: 'flex', gap: '30px', marginBottom: '30px', alignItems: 'stretch' }}>
        <div style={{ flex: 1, padding: '20px', background: 'transparent', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <RadarChart 
            data={radarData} 
            selectedAttributeName={selectedAttributeName} 
            onSelectAttribute={(name) => setSelectedAttributeName(name)} 
          />
        </div>

        <div style={{ flex: 1, border: '1px solid #e5e7eb', borderRadius: '12px', overflow: 'hidden', background: '#fff', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', borderBottom: '1px solid #e5e7eb' }}>
            <button 
              onClick={(e) => { e.preventDefault(); setSubTab('maintain'); }} 
              style={{ flex: 1, padding: '12px', background: subTab === 'maintain' ? '#f3f4f6' : '#fff', fontWeight: subTab === 'maintain' ? 'bold' : 'normal', border: 'none', borderRight: '1px solid #e5e7eb', cursor: 'pointer', color: '#333' }}
            >
              유지할 점
            </button>
            <button 
              onClick={(e) => { e.preventDefault(); setSubTab('improve'); }} 
              style={{ flex: 1, padding: '12px', background: subTab === 'improve' ? '#f3f4f6' : '#fff', fontWeight: subTab === 'improve' ? 'bold' : 'normal', border: 'none', borderRight: '1px solid #e5e7eb', cursor: 'pointer', color: '#333' }}
            >
              개선점
            </button>
            <button 
              onClick={(e) => { e.preventDefault(); setSubTab('neutral'); }} 
              style={{ flex: 1, padding: '12px', background: subTab === 'neutral' ? '#f3f4f6' : '#fff', fontWeight: subTab === 'neutral' ? 'bold' : 'normal', border: 'none', cursor: 'pointer', color: '#333' }}
            >
              중립
            </button>
          </div>
          {/* 오른쪽 요약 박스 스크롤 제거 및 좌측 정렬 적용 */}
          <div style={{ padding: '25px', flex: 1, color: '#4b5563', lineHeight: '1.6', textAlign: 'left' }}>
            <strong style={{ display: 'block', marginBottom: '10px', color: '#111', fontSize: '1.1rem' }}>
              [{currentAttributeReport.attribute_name || '선택된 속성'} 분석 요약]
            </strong>
            {renderFormattedSummary(currentSummary)}
          </div>
        </div>
      </div>

      {renderReviewBox()}
    </div>
  );

  const renderSentimentAnalysis = () => (
    <div>
      <div style={{ display: 'flex', gap: '40px', marginBottom: '30px', alignItems: 'stretch' }}>
        <div style={{ flex: 1, padding: '20px', background: 'transparent', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <SentimentPieChart stats={overallStats} sentimentTab={sentimentTab} onSelectTab={(tab) => setSentimentTab(tab)} />
        </div>

        <div style={{ flex: 1, border: '1px solid #e5e7eb', borderRadius: '12px', overflow: 'hidden', background: '#fff', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', borderBottom: '1px solid #e5e7eb' }}>
            <button onClick={(e) => { e.preventDefault(); setSentimentTab('positive'); }} style={{ flex: 1, padding: '12px', background: sentimentTab === 'positive' ? '#f3f4f6' : '#fff', fontWeight: sentimentTab === 'positive' ? 'bold' : 'normal', border: 'none', borderRight: '1px solid #e5e7eb', cursor: 'pointer' }}>유지할 점</button>
            <button onClick={(e) => { e.preventDefault(); setSentimentTab('negative'); }} style={{ flex: 1, padding: '12px', background: sentimentTab === 'negative' ? '#f3f4f6' : '#fff', fontWeight: sentimentTab === 'negative' ? 'bold' : 'normal', border: 'none', borderRight: '1px solid #e5e7eb', cursor: 'pointer' }}>개선할 점</button>
            <button onClick={(e) => { e.preventDefault(); setSentimentTab('neutral'); }} style={{ flex: 1, padding: '12px', background: sentimentTab === 'neutral' ? '#f3f4f6' : '#fff', fontWeight: sentimentTab === 'neutral' ? 'bold' : 'normal', border: 'none', borderRight: '1px solid #e5e7eb', cursor: 'pointer' }}>중립</button>
            <button onClick={(e) => { e.preventDefault(); setSentimentTab('all'); }} style={{ flex: 1, padding: '12px', background: sentimentTab === 'all' ? '#f3f4f6' : '#fff', fontWeight: sentimentTab === 'all' ? 'bold' : 'normal', border: 'none', cursor: 'pointer' }}>종합 요약</button>
          </div>
          {/* 오른쪽 요약 박스 스크롤 제거 및 좌측 정렬 적용 */}
          <div style={{ padding: '25px', flex: 1, minHeight: '180px', color: '#4b5563', lineHeight: '1.6', textAlign: 'left' }}>
            <strong style={{ display: 'block', marginBottom: '10px', color: '#111', fontSize: '1.1rem' }}>
              [{sentimentTab === 'positive' ? '유지할 점 종합 요약' : sentimentTab === 'negative' ? '개선점 종합 요약' : sentimentTab === 'neutral' ? '중립 안내' : '종합 요약'}]
            </strong>
            {renderFormattedSummary(currentOverallSummary)}
          </div>
        </div>
      </div>
      {renderReviewBox()}
    </div>
  );

  const renderReviews = () => (
    <div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '25px', borderBottom: '1px solid #eee', paddingBottom: '15px' }}>
        <div style={{ display: 'flex', gap: '15px', alignItems: 'center' }}>
          <span style={{ fontSize: '0.9rem', fontWeight: 'bold', color: '#333' }}>정렬 :</span>
          <button onClick={(e) => { e.preventDefault(); setReviewSort('all'); }} style={{ fontWeight: reviewSort === 'all' ? 'bold' : 'normal', background: 'none', border: 'none', cursor: 'pointer', color: reviewSort === 'all' ? '#1d4ed8' : '#666' }}>전체보기</button>
          <button onClick={(e) => { e.preventDefault(); setReviewSort('high'); }} style={{ fontWeight: reviewSort === 'high' ? 'bold' : 'normal', background: 'none', border: 'none', cursor: 'pointer', color: reviewSort === 'high' ? '#1d4ed8' : '#666' }}>별점 높은순</button>
          <button onClick={(e) => { e.preventDefault(); setReviewSort('low'); }} style={{ fontWeight: reviewSort === 'low' ? 'bold' : 'normal', background: 'none', border: 'none', cursor: 'pointer', color: reviewSort === 'low' ? '#1d4ed8' : '#666' }}>별점 낮은순</button>
        </div>

        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.9rem', fontWeight: 'bold', color: '#333', marginRight: '5px' }}>속성 :</span>
          <button 
            onClick={(e) => { e.preventDefault(); setSelectedAttributeFilter('all'); }} 
            style={{ padding: '4px 12px', borderRadius: '15px', border: '1px solid #d1d5db', background: selectedAttributeFilter === 'all' ? '#222' : '#fff', color: selectedAttributeFilter === 'all' ? '#fff' : '#555', cursor: 'pointer', fontSize: '0.85rem' }}
          >
            전체 속성
          </button>
          {radarData.map((attr, idx) => (
            <button
              key={`attr-filter-${idx}`}
              onClick={(e) => { e.preventDefault(); setSelectedAttributeFilter(attr.attribute_name); }}
              style={{
                padding: '4px 12px',
                borderRadius: '15px',
                border: '1px solid #93c5fd',
                background: selectedAttributeFilter === attr.attribute_name ? '#1d4ed8' : '#eff6ff',
                color: selectedAttributeFilter === attr.attribute_name ? '#fff' : '#1e40af',
                cursor: 'pointer',
                fontSize: '0.85rem'
              }}
            >
              {attr.attribute_name}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', maxHeight: '600px', overflowY: 'auto', paddingRight: '8px' }}>
        {detailedReviews && detailedReviews.length > 0 ? (
          detailedReviews.map((item) => (
            <div key={`review-detail-${item.review_id}`} style={{ borderBottom: '1px solid #e5e7eb', paddingBottom: '25px', marginBottom: '15px', background: '#fff', borderRadius: '12px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
              
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ color: '#e54747', fontSize: '0.95rem' }}>{'★'.repeat(item.rating)}{'☆'.repeat(5 - item.rating)}</span>
                      <span style={{ color: '#9498a0', fontSize: '0.85rem' }}>{item.review_date}</span>
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  {item.counts.positive > 0 && (
                    <span style={{ padding: '4px 10px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 'bold', border: '1px solid #bfdbfe', background: '#eff6ff', color: '#1e40af' }}>
                      🟢 긍정 {item.counts.positive}건
                    </span>
                  )}
                  {item.counts.negative > 0 && (
                    <span style={{ padding: '4px 10px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 'bold', border: '1px solid #fecaca', background: '#fef2f2', color: '#991b1b' }}>
                      🔴 부정 {item.counts.negative}건
                    </span>
                  )}
                  {item.counts.neutral > 0 && (
                    <span style={{ padding: '4px 10px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 'bold', border: '1px solid #a5a5a5', background: '#f9fafb', color: '#374151' }}>
                      🔘 중립 {item.counts.neutral}건
                    </span>
                  )}
                </div>
              </div>

              <div style={{ color: '#888', fontSize: '0.88rem', marginBottom: '10px', fontWeight: '500' }}>
                [옵션] {item.option_name}
              </div>

              <div style={{ color: '#222', fontSize: '0.98rem', lineHeight: '1.6', wordBreak: 'keep-all', textAlign: 'left' }}>
                {renderHighlightedReviewText(item.review_content, item.sentences)}
              </div>
            </div>
          ))
        ) : (
          <div style={{ border: '1px solid #e5e7eb', padding: '40px', borderRadius: '10px', background: '#fff', textAlign: 'center', color: '#888' }}>
            해당 조건과 일치하는 리뷰 데이터가 없습니다.
          </div>
        )}
      </div>
    </div>
  );

  const renderReviewBox = () => (
    <div>
      <div style={{ marginBottom: '12px', fontSize: '0.9rem', display: 'flex', gap: '15px' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer', color: '#555' }}>
          <input 
            type="checkbox" 
            checked={showSentimentSentence} 
            onChange={(e) => setShowSentimentSentence(e.target.checked)} 
          /> 감성분석 문장보기
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer', color: '#555' }}>
          <input 
            type="checkbox" 
            checked={showFullReview} 
            onChange={(e) => setShowFullReview(e.target.checked)} 
          /> 리뷰원문보기
        </label>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '15px', maxHeight: '550px', overflowY: 'auto', paddingRight: '8px' }}>
        {reviewsData && reviewsData.length > 0 ? (
          reviewsData.map((item, idx) => {
            let sentColor = '#1d4ed8';
            let sentBg = '#eff6ff';
            if (item.sentiment_label === 'negative') {
              sentColor = '#dc2626';
              sentBg = '#fef2f2';
            } else if (item.sentiment_label === 'neutral') {
              sentColor = '#4b5563';
              sentBg = '#f3f4f6';
            }

            return (
              <div key={`review-card-${item.review_id}-${item.sequence_no}-${idx}`} style={{ border: '1px solid #e5e7eb', padding: '20px', borderRadius: '10px', background: '#fff' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px', fontSize: '0.9rem' }}>
                  <span style={{ color: '#eab308' }}>{'★'.repeat(item.rating)}{'☆'.repeat(5 - item.rating)}</span>
                  <span style={{ color: '#888' }}>옵션: {item.option_name} | 작성일: {item.review_created_at}</span>
                </div>
                
                {/* 분석 문장 + 속성 라벨 배지 표기 */}
                {showSentimentSentence && item.sentiment_sentence && (
                  <div style={{ color: sentColor, margin: '0 0 8px 0', fontWeight: '500', background: sentBg, padding: '8px 12px', borderRadius: '6px', textAlign: 'left', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 'bold' }}>📄 [전처리 분석 문장]:</span>
                    {item.attribute_name && (
                      <span style={{ fontSize: '0.75rem', fontWeight: 'bold', padding: '2px 6px', backgroundColor: '#fff', color: sentColor, borderRadius: '4px', border: `1px solid ${sentColor}` }}>
                        {item.attribute_name}
                      </span>
                    )}
                    <span>"{item.sentiment_sentence}"</span>
                  </div>
                )}

                {/* 리뷰 원문 + 하이라이팅 및 속성 라벨, 줄바꿈 적용 */}
                {showFullReview && item.full_review_text && (
                  <div style={{ color: '#333', margin: 0, fontSize: '0.95rem', background: '#f9fafb', padding: '10px 12px', borderRadius: '6px', textAlign: 'left', lineHeight: '1.6' }}>
                    <span style={{ display: 'block', fontWeight: 'bold', marginBottom: '6px', color: '#111' }}>
                      💬 [리뷰 원문]
                    </span>
                    {renderHighlightedReviewText(item.full_review_text, [
                      { 
                        separated_sentence: item.sentiment_sentence, 
                        sentiment_label: item.sentiment_label, 
                        attribute_name: item.attribute_name 
                      }
                    ])}
                  </div>
                )}
              </div>
            );
          })
        ) : (
          <div style={{ border: '1px solid #e5e7eb', padding: '30px', borderRadius: '10px', background: '#fff', textAlign: 'center', color: '#888' }}>
            해당 조건과 일치하는 리뷰 데이터가 없습니다.
          </div>
        )}
      </div>
    </div>
  );

  if (loading) return <div style={{ padding: '50px', textAlign: 'center' }}>데이터를 불러오는 중입니다...</div>;
  if (!productData) return <div style={{ padding: '50px', textAlign: 'center' }}>상품 정보를 찾을 수 없습니다.</div>;

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '40px 20px', fontFamily: 'sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: '40px' }}>
        <button 
          onClick={onBack} 
          style={{ 
            display: 'inline-flex', 
            alignItems: 'center', 
            gap: '8px', 
            background: 'transparent', 
            color: '#555', 
            border: 'none', 
            fontSize: '1rem', 
            cursor: 'pointer', 
            padding: '0',
            fontWeight: '500'
          }}
        >
          <span style={{ fontSize: '1.2rem' }}>←</span> 상품 목록으로
        </button>
      </div>
      
      <div style={{ display: 'flex', gap: '40px', marginBottom: '50px', alignItems: 'flex-start' }}>
        <div style={{ flex: 1, display: 'flex' }}>
          <div style={{ width: '100%', aspectRatio: '1 / 1', background: '#f9fafb', borderRadius: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid #eee', overflow: 'hidden' }}>
            {productData.product_image_url ? (
              <img src={productData.product_image_url} alt={productData.product_name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            ) : (
              <span style={{ color: '#aaa' }}>이미지 없음</span>
            )}
          </div>
        </div>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div>
            <div style={{ fontSize: '0.95rem', color: '#888', marginBottom: '8px' }}>{productData.brand_name || '타사 브랜드'}</div>
            <h2 style={{ fontSize: '1.7rem', margin: 0, color: '#111', lineHeight: '1.35', wordBreak: 'keep-all' }}>
              {productData.product_name}
            </h2>
          </div>
          
          <div style={{ border: '1px solid #e5e7eb', padding: '20px', borderRadius: '10px', background: '#fff' }}>
            <h3 style={{ margin: '0 0 12px 0', fontSize: '1rem', color: '#333', textAlign: 'center' }}>상품 옵션</h3>
            {options && options.length > 0 ? (
              <ol style={{ margin: 0, paddingLeft: '20px', lineHeight: '1.8', color: '#555' }}>
                {options.map((opt) => (
                  <li key={opt.product_option_id} style={{ paddingLeft: '4px' }}>{opt.option_name}</li>
                ))}
              </ol>
            ) : (
              <p style={{ margin: 0, color: '#888', textAlign: 'center' }}>옵션이 없습니다.</p>
            )}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '10px', marginBottom: '30px', borderBottom: '2px solid #222' }}>
        {[
          { id: 'maintainProduct', label: '속성별 유지/개선점 분석' },
          { id: 'sentiment', label: '모든 속성 유지/개선점 분석' },
          { id: 'reviews', label: '모든 리뷰 보기' }
        ].map(menu => (
          <button 
            key={menu.id}
            onClick={(e) => { e.preventDefault(); setActiveMenu(menu.id); }}
            style={{
              flex: 1,
              padding: '14px 20px',
              textAlign: 'center',
              fontSize: '1rem',
              border: 'none',
              borderRadius: '8px 8px 0 0',
              background: activeMenu === menu.id ? '#222' : '#f3f4f6',
              color: activeMenu === menu.id ? '#fff' : '#666',
              fontWeight: activeMenu === menu.id ? 'bold' : 'normal',
              cursor: 'pointer',
              transition: 'all 0.2s'
            }}
          >
            {menu.label}
          </button>
        ))}
      </div>

      <div>
        {activeMenu === 'maintainProduct' && renderMaintainProduct()}
        {activeMenu === 'sentiment' && renderSentimentAnalysis()}
        {activeMenu === 'reviews' && renderReviews()}
      </div>
    </div>
  );
};

export default BaseProductDetail;