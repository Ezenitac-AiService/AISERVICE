import React, { useState } from 'react';
import BaseProductDetail from './BaseProductDetail';

function CompetitorProductDetailPage({ onNavigate, subscription, apiBaseUrl, onBack, productId: propProductId }) {
  const [productId, setProductId] = useState(() => {
    if (propProductId) return propProductId;
    // 🌟 타사 상품 상세 진입 시 저장되는 'oliview_selectedCompetitorProduct'에서 ID 추출
    try {
      // 🌟 localStorage -> sessionStorage로 변경
      const savedCompetitorProduct = sessionStorage.getItem('oliview_selectedCompetitorProduct');
      if (savedCompetitorProduct) {
        const parsed = JSON.parse(savedCompetitorProduct);
        if (parsed.product_id) return parsed.product_id;
        if (parsed.id) return parsed.id;
      }
    } catch (e) {
      console.error('타사 상품 정보 파싱 실패:', e);
    }

    // 🌟 localStorage -> sessionStorage로 변경
    return sessionStorage.getItem('oliview_selectedProduct_id') || null;
  });

  React.useEffect(() => {
    if (propProductId && propProductId !== productId) {
      setProductId(propProductId);
    }
  }, [propProductId, productId]);

  const handleBack = (e) => {
    e.preventDefault();
    // 🌟 localStorage -> sessionStorage로 변경
    sessionStorage.removeItem('oliview_selectedProduct_id');
    sessionStorage.removeItem('oliview_selectedProduct');
    sessionStorage.removeItem('oliview_selectedCompetitorProduct');
    sessionStorage.removeItem('oliview_myBrand_selectedProductId');
    
    if (onBack) {
      onBack(e);
    } else {
      onNavigate('competitorDashboard');
    }
  };

  if (!productId) {
    return (
      <div style={{ padding: '100px', textAlign: 'center' }}>
        상품 ID를 찾을 수 없습니다. 다시 시도해주세요.
      </div>
    );
  }

  return (
    <BaseProductDetail 
      productId={productId} 
      onBack={handleBack} 
      apiBaseUrl={apiBaseUrl || '/bteam/oliview'} 
    />
  );
}

export default CompetitorProductDetailPage;