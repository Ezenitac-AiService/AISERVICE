import React, { useState, useEffect, useRef } from 'react';
import './MyBrandPage.css';
import ProductDetailPage from './ProductDetailPage';

// 🌟 커스텀 드롭다운 컴포넌트
const CustomDropdown = ({ value, onChange, options, placeholder, disabled }) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const selectedOption = options.find(opt => String(opt.value) === String(value));
  const displayLabel = selectedOption ? selectedOption.label : placeholder;

  return (
    <div ref={dropdownRef} style={{ position: 'relative', minWidth: '200px' }}>
      <div
        onClick={() => !disabled && setIsOpen(!isOpen)}
        style={{
          padding: '12px 20px',
          borderRadius: '25px',
          border: '1px solid #cbd5e1',
          backgroundColor: disabled ? '#f8fafc' : '#fff',
          fontSize: '0.95rem',
          color: disabled ? '#94a3b8' : '#333',
          cursor: disabled ? 'not-allowed' : 'pointer',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          boxShadow: '0 2px 5px rgba(0,0,0,0.02)',
          opacity: disabled ? 0.5 : 1,
          userSelect: 'none'
        }}
      >
        <span>{displayLabel}</span>
        <span style={{ fontSize: '0.8rem', color: '#64748b', transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}>▼</span>
      </div>

      {isOpen && !disabled && (
        <div style={{
          position: 'absolute',
          top: 'calc(100% + 8px)',
          left: 0,
          width: '100%',
          backgroundColor: '#fff',
          border: '1px solid #cbd5e1',
          borderRadius: '16px',
          boxShadow: '0 10px 25px rgba(0,0,0,0.08)',
          zIndex: 100,
          maxHeight: '260px',
          overflowY: 'auto',
          padding: '6px 0'
        }}>
          {options.map((opt) => {
            const isSelected = String(opt.value) === String(value);
            return (
              <div
                key={opt.value}
                onClick={() => {
                  onChange(opt.value);
                  setIsOpen(false);
                }}
                style={{
                  padding: '10px 18px',
                  fontSize: '0.92rem',
                  color: isSelected ? '#1d4ed8' : '#333',
                  backgroundColor: isSelected ? '#eff6ff' : 'transparent',
                  fontWeight: isSelected ? 'bold' : 'normal',
                  cursor: 'pointer',
                  transition: 'background 0.15s'
                }}
                onMouseEnter={(e) => { if (!isSelected) e.currentTarget.style.backgroundColor = '#f8fafc'; }}
                onMouseLeave={(e) => { if (!isSelected) e.currentTarget.style.backgroundColor = 'transparent'; }}
              >
                {opt.label}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

function MyBrandPage({ user, onNavigate, apiBaseUrl }) {
  const baseUrl = apiBaseUrl || '/bteam/oliview';
  const [categories, setCategories] = useState([]);
  const [products, setProducts] = useState([]);
  const [allProducts, setAllProducts] = useState([]); // 🌟 카테고리별 개수 계산용 전체 상품
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [loading, setLoading] = useState(true);

  const [selectedProductId, setSelectedProductId] = useState(() => {
    // 🌟 localStorage -> sessionStorage로 변경
    const savedId = sessionStorage.getItem('oliview_selectedProduct_id');
    return savedId ? Number(savedId) : null;
  });

  const [selectedLevel1, setSelectedLevel1] = useState('all');
  const [selectedLevel2, setSelectedLevel2] = useState('all');
  const [selectedLevel3, setSelectedLevel3] = useState('all');

  // 1. 카테고리 불러오기
  useEffect(() => {
    fetch(`${baseUrl}/api/brands/${user.brandId}/categories`)
      .then((res) => res.json())
      .then((data) => {
        if (data.success) setCategories(data.categories);
      })
      .catch((err) => console.error('카테고리 불러오기 실패:', err));
  }, [user.brandId, baseUrl]);

  // 2. 브랜드 전체 상품 정보 (갯수 집계 전용)
  useEffect(() => {
    fetch(`${baseUrl}/api/brands/${user.brandId}/products`)
      .then((res) => res.json())
      .then((data) => {
        if (data.success) setAllProducts(data.products);
      })
      .catch((err) => console.error('전체 상품 불러오기 실패:', err));
  }, [user.brandId, baseUrl]);

  // 3. 선택된 필터 기준 상품 불러오기
  useEffect(() => {
    setLoading(true);
    const url = selectedCategory === 'all'
      ? `${baseUrl}/api/brands/${user.brandId}/products`
      : `${baseUrl}/api/brands/${user.brandId}/products?categoryId=${selectedCategory}`;

    fetch(url)
      .then((res) => res.json())
      .then((data) => {
        if (data.success) setProducts(data.products);
        setLoading(false);
      })
      .catch((err) => {
        console.error('상품 불러오기 실패:', err);
        setLoading(false);
      });
  }, [user.brandId, selectedCategory, baseUrl]);

  // 🌟 카테고리 및 하위 카테고리 포함 총 상품 갯수 계산 함수
  const getCategoryProductCount = (catId) => {
    if (!allProducts || allProducts.length === 0) return 0;
    if (catId === 'all') return allProducts.length;

    const getSubCategoryIds = (targetId) => {
      let ids = [String(targetId)];
      let queue = [String(targetId)];
      while (queue.length > 0) {
        const currentId = queue.shift();
        const children = categories.filter(c => String(c.parent_category_id) === currentId);
        children.forEach(child => {
          const childIdStr = String(child.category_id);
          if (!ids.includes(childIdStr)) {
            ids.push(childIdStr);
            queue.push(childIdStr);
          }
        });
      }
      return ids;
    };

    const targetCategoryIds = getSubCategoryIds(catId);

    return allProducts.filter(p => {
      if (!p.category_ids) return false;
      const pCatIds = String(p.category_ids).split(',').map(id => id.trim());
      return targetCategoryIds.some(id => pCatIds.includes(id));
    }).length;
  };

  const level1Categories = categories.filter(c => c.category_level === 1);
  const level2Categories = categories.filter(c => c.category_level === 2 && String(c.parent_category_id) === String(selectedLevel1));
  const level3Categories = categories.filter(c => c.category_level === 3 && String(c.parent_category_id) === String(selectedLevel2));

  const handleLevel1Change = (value) => {
    setSelectedLevel1(value);
    setSelectedLevel2('all');
    setSelectedLevel3('all');
    setSelectedCategory(value);
  };

  const handleLevel2Change = (value) => {
    setSelectedLevel2(value);
    setSelectedLevel3('all');
    setSelectedCategory(value === 'all' ? selectedLevel1 : value);
  };

  const handleLevel3Change = (value) => {
    setSelectedLevel3(value);
    setSelectedCategory(value === 'all' ? (selectedLevel2 === 'all' ? selectedLevel1 : selectedLevel2) : value);
  };

  const handleSelectProduct = (productId) => {
    setSelectedProductId(productId);
    // 🌟 localStorage -> sessionStorage로 변경
    sessionStorage.setItem('oliview_selectedProduct_id', productId);
  };
  
  const handleBackToProductList = () => {
    setSelectedProductId(null);
    // 🌟 localStorage -> sessionStorage로 변경
    sessionStorage.removeItem('oliview_selectedProduct_id');
  };

  if (selectedProductId !== null) {
    return (
      <ProductDetailPage 
        productId={selectedProductId} 
        onBack={handleBackToProductList} 
        onNavigate={onNavigate} 
        apiBaseUrl={baseUrl}
      />
    );
  }

  return (
    <div className="my-brand-container">
      <header className="brand-header" style={{ textAlign: 'center', marginBottom: '30px' }}>
        <h2 style={{ fontSize: '1.8rem', fontWeight: 'bold', color: '#111', marginBottom: '8px' }}>
          내 브랜드 상품 분석
        </h2>
        <p style={{ color: '#666', fontSize: '1rem' }}>
          내 브랜드 상품 분석 페이지 입니다. 원하시는 상품을 선택해보세요.
        </p>
      </header>

      {/* 🌟 드롭다운 영역 (개수 표기 추가) */}
      <div className="category-dropdown-section" style={{ display: 'flex', justifyContent: 'center', gap: '15px', marginBottom: '40px' }}>
        <CustomDropdown
          value={selectedLevel1}
          onChange={handleLevel1Change}
          placeholder="전체보기 (대분류)"
          options={[
            { value: 'all', label: `전체보기 (대분류) (${allProducts.length}개)` },
            ...level1Categories.map(cat => ({
              value: cat.category_id,
              label: `${cat.category_name} (${getCategoryProductCount(cat.category_id)}개)`
            }))
          ]}
        />

        <CustomDropdown
          value={selectedLevel2}
          onChange={handleLevel2Change}
          placeholder="전체보기 (중분류)"
          disabled={selectedLevel1 === 'all'}
          options={[
            { value: 'all', label: `전체보기 (중분류) (${selectedLevel1 !== 'all' ? getCategoryProductCount(selectedLevel1) : 0}개)` },
            ...level2Categories.map(cat => ({
              value: cat.category_id,
              label: `${cat.category_name} (${getCategoryProductCount(cat.category_id)}개)`
            }))
          ]}
        />

        <CustomDropdown
          value={selectedLevel3}
          onChange={handleLevel3Change}
          placeholder="전체보기 (소분류)"
          disabled={selectedLevel2 === 'all'}
          options={[
            { value: 'all', label: `전체보기 (소분류) (${selectedLevel2 !== 'all' ? getCategoryProductCount(selectedLevel2) : 0}개)` },
            ...level3Categories.map(cat => ({
              value: cat.category_id,
              label: `${cat.category_name} (${getCategoryProductCount(cat.category_id)}개)`
            }))
          ]}
        />
      </div>

      {loading ? (
        <div className="loading-text">상품 정보를 불러오는 중입니다...</div>
      ) : (
        <div className="product-grid">
          {products.length > 0 ? (
            products.map((product) => (
              <div 
                key={product.product_id} 
                className="product-card"
                onClick={() => handleSelectProduct(product.product_id)}
              >
                <div className="product-image-box">
                  {product.product_image_url ? (
                    <img src={product.product_image_url} alt={product.product_name} />
                  ) : (
                    <div className="no-image">No Image</div>
                  )}
                </div>
                <div className="product-info">
                  <div className="product-brand-name">{product.brand_name}</div>
                  <div className="product-name">{product.product_name}</div>
                </div>
              </div>
            ))
          ) : (
            <div className="no-products">해당 카테고리에 등록된 상품이 없습니다.</div>
          )}
        </div>
      )}
    </div>
  );
}

export default MyBrandPage;