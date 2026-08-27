import React, { useState } from 'react';
import BaseProductDetail from './BaseProductDetail';

// 🌟 onBack 및 productId 파라미터를 직접 받을 수 있도록 개선합니다.
function ProductDetailPage({ onNavigate, subscription, apiBaseUrl, onBack, productId: propProductId }) {
  const [productId, setProductId] = useState(() => {
    return propProductId || sessionStorage.getItem('oliview_selectedProduct_id') || null;
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
    sessionStorage.removeItem('oliview_myBrand_selectedProductId');
    
    // 🌟 MyBrandPage에서 넘겨준 onBack 함수가 있으면 실행하여 목록으로 돌아갑니다.
    if (onBack) {
      onBack(e);
    } else {
      onNavigate('myBrand');
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

export default ProductDetailPage;