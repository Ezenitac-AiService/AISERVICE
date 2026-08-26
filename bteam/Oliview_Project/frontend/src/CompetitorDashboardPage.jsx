import React, { useState, useEffect, useRef } from 'react';

const matchInitialFilter = (brandName, filter) => {
  if (!filter || filter === '전체') return true;
  const firstChar = brandName.trim().charAt(0);
  if (!firstChar) return false;

  if (/^[A-Za-z]$/.test(filter)) {
    return firstChar.toUpperCase() === filter.toUpperCase();
  }

  const code = firstChar.charCodeAt(0) - 44032;
  const initialsMap = ['ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'];

  if (code >= 0 && code <= 11171) {
    const initialIdx = Math.floor(code / 588);
    const initialChar = initialsMap[initialIdx];

    if (filter === '기타') return false;
    if (filter === 'ㄱ' && (initialChar === 'ㄱ' || initialChar === 'ㄲ')) return true;
    if (filter === 'ㄷ' && (initialChar === 'ㄷ' || initialChar === 'ㄸ')) return true;
    if (filter === 'ㅂ' && (initialChar === 'ㅂ' || initialChar === 'ㅃ')) return true;
    if (filter === 'ㅅ' && (initialChar === 'ㅅ' || initialChar === 'ㅆ')) return true;
    if (filter === 'ㅈ' && (initialChar === 'ㅈ' || initialChar === 'ㅉ')) return true;
    return initialChar === filter;
  }

  if (filter === '기타') {
    const isKorean = code >= 0 && code <= 11171;
    const isEnglish = /^[A-Za-z]$/.test(firstChar);
    return !isKorean && !isEnglish;
  }

  return false;
};

const getActiveBillingCycle = (startDateStr) => {
  const start = startDateStr ? new Date(startDateStr) : new Date();
  const now = new Date();

  let cycleIndex = 0;
  let cycleStart = new Date(start);
  let cycleEnd = new Date(start);
  cycleEnd.setMonth(cycleEnd.getMonth() + 1);
  cycleEnd.setDate(cycleEnd.getDate() - 1);

  while (now > cycleEnd) {
    cycleIndex++;
    cycleStart = new Date(cycleEnd);
    cycleStart.setDate(cycleStart.getDate() + 1);
    cycleEnd = new Date(cycleStart);
    cycleEnd.setMonth(cycleEnd.getMonth() + 1);
    cycleEnd.setDate(cycleEnd.getDate() - 1);
  }

  const formatDate = (d) => `${d.getFullYear()}.${d.getMonth() + 1}.${d.getDate()}`;

  return {
    cycleKey: `cycle_${cycleIndex}_${startDateStr || 'default'}`,
    cycleIndex,
    startDateStr: formatDate(cycleStart),
    endDateStr: formatDate(cycleEnd),
    prevCycleKey: cycleIndex > 0 ? `cycle_${cycleIndex - 1}_${startDateStr || 'default'}` : null
  };
};

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

function CompetitorDashboardPage({ onNavigate, subscription, setSubscription, user, apiBaseUrl }) {
  const baseUrl = apiBaseUrl || '/bteam/oliview';
  const [view, setView] = useState(() => {
    // 🌟 localStorage -> sessionStorage로 변경
    return sessionStorage.getItem('oliview_comp_view') || 'brands';
  });
  
  const [selectedBrand, setSelectedBrand] = useState(() => {
    // 🌟 localStorage -> sessionStorage로 변경
    const saved = sessionStorage.getItem('oliview_comp_selectedBrand');
    return saved ? JSON.parse(saved) : null;
  });

  const [competitorBrands, setCompetitorBrands] = useState([]);
  const [products, setProducts] = useState([]);
  const [allProducts, setAllProducts] = useState([]);
  
  const [sortOrder, setSortOrder] = useState('asc');
  const [selectedInitial, setSelectedInitial] = useState('전체');
  const [searchTerm, setSearchTerm] = useState('');

  const [subscriptionStartDate, setSubscriptionStartDate] = useState('');
  const myBrandId = user?.brandId;

  useEffect(() => {
    if (myBrandId) {
      fetch(`${baseUrl}/api/subscription/${myBrandId}`)
        .then(res => res.json())
        .then(data => {
          if (data.success && data.subscription) {
            const sub = data.subscription;
            if (sub.isSubscribed && sub.status === 'ACTIVE' && sub.planName) {
              setSubscriptionStartDate(sub.paidAt);
              if (setSubscription) setSubscription(sub.planName);
            } else {
              if (setSubscription) setSubscription(null);
              setSubscriptionStartDate('');
            }
          } else {
            if (setSubscription) setSubscription(null);
            setSubscriptionStartDate('');
          }
        })
        .catch(err => {
          console.error('구독 정보 동기화 실패:', err);
          if (setSubscription) setSubscription(null);
        });
    }
  }, [myBrandId, baseUrl, setSubscription]);

  const activeCycle = getActiveBillingCycle(subscriptionStartDate || new Date().toISOString().split('T')[0]);

  const planDetails = {
    '베이비': { type: 'count', total: 3 },
    '핑크': { type: 'count', total: 7 },
    '그린': { type: 'count', total: 15 },
    '블랙': { type: 'category', maxCategories: 1, changeFee: 100000 },
    '골드': { type: 'category', maxCategories: 2, changeFee: 0 }
  };

  const currentPlan = planDetails[subscription] || { type: 'count', total: 0 };

  const [categorySubData, setCategorySubData] = useState({ selectedCategories: [], changeCount: 0 });
  const currentCategoryData = categorySubData;

  const [isCategoryModalOpen, setIsCategoryModalOpen] = useState(false);
  const [tempCategorySelections, setTempCategorySelections] = useState([]);
  const [categories, setCategories] = useState([]);

  const allMainCategories = categories.filter(c => c.category_level === 1);

  const [cycleRecords, setCycleRecords] = useState({});

  useEffect(() => {
    if (myBrandId && activeCycle.cycleKey) {
      fetch(`${baseUrl}/api/competitor/views/${myBrandId}?cycleKey=${activeCycle.cycleKey}`)
        .then(res => res.json())
        .then(data => {
          if (data.success) {
            setCycleRecords(prev => ({ ...prev, [activeCycle.cycleKey]: data.views }));
          }
        })
        .catch(err => console.error('열람 기록 로드 실패:', err));

      if (activeCycle.prevCycleKey) {
        fetch(`${baseUrl}/api/competitor/views/${myBrandId}?cycleKey=${activeCycle.prevCycleKey}`)
          .then(res => res.json())
          .then(data => {
            if (data.success) {
              setCycleRecords(prev => ({ ...prev, [activeCycle.prevCycleKey]: data.views }));
            }
          })
          .catch(err => console.error('전월 열람 기록 로드 실패:', err));
      }

      fetch(`${baseUrl}/api/competitor/categories/${myBrandId}?cycleKey=${activeCycle.cycleKey}`)
        .then(res => res.json())
        .then(data => {
          if (data.success) {
            setCategorySubData({
              selectedCategories: data.selectedCategories || [],
              changeCount: data.changeCount || 0
            });
          }
        })
        .catch(err => console.error('카테고리 정보 로드 실패:', err));
    }
  }, [myBrandId, activeCycle.cycleKey, activeCycle.prevCycleKey, baseUrl]);

  const currentViews = cycleRecords[activeCycle.cycleKey] || [];
  const prevViews = activeCycle.prevCycleKey ? (cycleRecords[activeCycle.prevCycleKey] || []) : [];

  const prevViewedInCurrent = currentViews.filter(item => prevViews.some(p => p.id === item.id));
  const hasGreenFreeBenefit = subscription === '그린' && prevViewedInCurrent.length > 0;
  const freeCount = hasGreenFreeBenefit ? 1 : 0;

  const usedCount = Math.max(0, currentViews.length - freeCount);
  const remaining = currentPlan.type === 'count' ? currentPlan.total - usedCount : '무제한';

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 20;

  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedLevel1, setSelectedLevel1] = useState('all');
  const [selectedLevel2, setSelectedLevel2] = useState('all');
  const [selectedLevel3, setSelectedLevel3] = useState('all');

  const myBrandName = user?.brandName || '차앤박'; 

  const koreanInitials = ['전체', 'ㄱ', 'ㄴ', 'ㄷ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅅ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ', '기타'];
  const englishAlphabets = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'];

  useEffect(() => {
    fetch(`${baseUrl}/api/brands`)
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          const filtered = data.brands.filter(b => b.brand_id !== myBrandId && b.brand_name !== myBrandName);
          setCompetitorBrands(filtered);
        }
      })
      .catch(() => setCompetitorBrands([]));
  }, [myBrandId, myBrandName, baseUrl]);

  useEffect(() => {
    fetch(`${baseUrl}/api/brands/${myBrandId}/categories`) 
      .then((res) => res.json())
      .then((data) => {
        if (data.success) setCategories(data.categories);
      })
      .catch((err) => console.error('카테고리 불러오기 실패:', err));
  }, [myBrandId, baseUrl]);

  useEffect(() => {
    if (view === 'products' && selectedBrand) {
      fetch(`${baseUrl}/api/brands/${selectedBrand.brand_id}/products`)
        .then(res => res.json())
        .then(data => {
          if (data.success) setAllProducts(data.products);
        })
        .catch(() => setAllProducts([]));
    }
  }, [selectedBrand, view, baseUrl]);

  useEffect(() => {
    if (view === 'products' && selectedBrand) {
      const url = selectedCategory === 'all'
      ? `${baseUrl}/api/brands/${selectedBrand.brand_id}/products`
      : `${baseUrl}/api/brands/${selectedBrand.brand_id}/products?categoryId=${selectedCategory}`;
      
      fetch(url)
        .then(res => res.json())
        .then(data => {
          if (data.success) setProducts(data.products);
        })
        .catch(() => setProducts([]));
    }
  }, [selectedBrand, selectedCategory, view, baseUrl]);

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

  const handleBrandClick = (brand) => {
    if (!subscription) {
      alert('타사 브랜드 상품 분석을 이용하려면 먼저 구독 플랜을 가입해 주세요.');
      onNavigate('subscription');
      return;
    }

    setSelectedBrand(brand);
    setView('products'); 
    // 🌟 localStorage -> sessionStorage로 변경
    sessionStorage.setItem('oliview_comp_view', 'products');
    sessionStorage.setItem('oliview_comp_selectedBrand', JSON.stringify(brand));
    setSelectedLevel1('all');
    setSelectedLevel2('all');
    setSelectedLevel3('all');
    setSelectedCategory('all');
  };

  const handleBackToBrands = () => {
    setView('brands');
    setSelectedBrand(null);
    // 🌟 localStorage -> sessionStorage로 변경
    sessionStorage.setItem('oliview_comp_view', 'brands');
    sessionStorage.removeItem('oliview_comp_selectedBrand');
  };

  const level1Categories = categories.filter(c => c.category_level === 1);
  const level2Categories = categories.filter(c => c.category_level === 2 && String(c.parent_category_id) === String(selectedLevel1));
  const level3Categories = categories.filter(c => c.category_level === 3 && String(c.parent_category_id) === String(selectedLevel2));

  const handleLevel1Change = (value) => {
    setSelectedLevel1(value);
    setSelectedLevel2('all');
    setSelectedLevel3('all');
    setSelectedCategory(value === 'all' ? 'all' : value);
  };

  const handleLevel2Change = (value) => {
    setSelectedLevel2(value);
    setSelectedLevel3('all');
    setSelectedCategory(value === 'all' ? (selectedLevel1 === 'all' ? 'all' : selectedLevel1) : value);
  };

  const handleLevel3Change = (value) => {
    setSelectedLevel3(value);
    setSelectedCategory(value === 'all' ? (selectedLevel2 === 'all' ? selectedLevel2 : selectedLevel1) : value);
  };

  const handleProductClick = (product) => {
    if (!subscription) {
      alert('구독 플랜이 만료되었거나 해지되었습니다. 구독 후 이용해 주세요.');
      onNavigate('subscription');
      return;
    }

    if (currentPlan.type === 'category') {
      const selectedCatIds = currentCategoryData.selectedCategories.map(c => String(c.id).trim());
      const selectedCatNames = currentCategoryData.selectedCategories.map(c => c.name.trim());
    
      if (selectedCatIds.length === 0) {
        alert('상단 구독 현황 카드에서 먼저 이용하실 카테고리를 선택해주세요.');
        return;
      }
    
      const productCatIds = product.category_ids 
        ? (typeof product.category_ids === 'string' 
            ? product.category_ids.split(',').map(id => String(id).trim()) 
            : [String(product.category_ids).trim()])
        : [];

      let productPathIds = [];
      let productPathNames = [];

      productCatIds.forEach(catId => {
        let currentCat = categories.find(c => String(c.category_id).trim() === String(catId).trim());
        while (currentCat) {
          productPathIds.push(String(currentCat.category_id).trim());
          if (currentCat.category_name) {
            productPathNames.push(currentCat.category_name.trim());
          }
          const parentIdStr = currentCat.parent_category_id ? String(currentCat.parent_category_id).trim() : '';
          if (!parentIdStr || parentIdStr === '0' || Number(currentCat.category_level) === 1) {
            break;
          }
          currentCat = categories.find(c => String(c.category_id).trim() === parentIdStr);
        }
      });

      const isAllowedById = productPathIds.some(id => selectedCatIds.includes(id));
      const isAllowedByName = productPathNames.some(name => selectedCatNames.includes(name));

      if (!isAllowedById && !isAllowedByName) {
        alert(`선택하지 않은 카테고리의 상품입니다.\n현재 지정된 카테고리[ ${currentCategoryData.selectedCategories.map(c => c.name).join(', ')} ] 내 상품만 무제한 열람이 가능합니다.`);
        return;
      }
    } else {
      const isAlreadyViewedInThisCycle = currentViews.some(item => item.id === product.product_id);

      if (!isAlreadyViewedInThisCycle) {
        const isPrevViewed = prevViews.some(p => p.id === product.product_id);
        const appliesGreenFree = subscription === '그린' && isPrevViewed && prevViewedInCurrent.length === 0;

        if (!appliesGreenFree && usedCount >= currentPlan.total) {
          alert(`현재 구독 주기(${activeCycle.startDateStr} ~ ${activeCycle.endDateStr})의 열람 가능 횟수(${currentPlan.total}개)를 모두 소진하셨습니다.`);
          return; 
        }

        const newItem = {
          id: product.product_id,
          name: product.product_name,
          brandName: selectedBrand?.brand_name || '타사 브랜드',
          imageUrl: product.product_image_url,
          fullProduct: product,
          isFreeBenefit: appliesGreenFree
        };

        fetch(`${baseUrl}/api/competitor/views`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            brandId: myBrandId,
            cycleKey: activeCycle.cycleKey,
            item: newItem
          })
        })
        .then(res => res.json())
        .then(data => {
          if (data.success) {
            const updatedViews = [...currentViews, newItem];
            setCycleRecords(prev => ({ ...prev, [activeCycle.cycleKey]: updatedViews }));
          }
        })
        .catch(err => console.error('열람 기록 저장 실패:', err));

        if (appliesGreenFree) alert('그린 플랜 혜택이 적용되어 전월 열람 상품 1개 미차감 처리되었습니다!');
      }
    }
  
    // 🌟 localStorage -> sessionStorage로 변경
    sessionStorage.setItem('oliview_selectedCompetitorProduct', JSON.stringify(product));
    onNavigate('competitorProductDetail');
  };

  const handleOpenCategoryModal = () => {
    const isInitial = currentCategoryData.selectedCategories.length === 0;
    if (!isInitial && currentCategoryData.changeCount >= 1) {
      alert('이번 구독 주기(월 1회)의 카테고리 변경 횟수를 이미 모두 사용하셨습니다.');
      return;
    }
    setTempCategorySelections([...currentCategoryData.selectedCategories]);
    setIsCategoryModalOpen(true);
  };

  const handleToggleCategorySelect = (cat) => {
    const max = currentPlan.maxCategories;
    const exists = tempCategorySelections.some(c => c.id === cat.category_id);
    if (exists) {
      setTempCategorySelections(tempCategorySelections.filter(c => c.id !== cat.category_id));
    } else {
      if (tempCategorySelections.length >= max) {
        alert(`${subscription} 플랜은 최대 ${max}개의 카테고리만 선택 가능합니다.`);
        return;
      }
      setTempCategorySelections([...tempCategorySelections, { id: cat.category_id, name: cat.category_name }]);
    }
  };

  const handleSaveCategorySelection = () => {
    const isInitial = currentCategoryData.selectedCategories.length === 0;
    const max = currentPlan.maxCategories;
    if (tempCategorySelections.length < max) {
      alert(`카테고리를 ${max}개 선택해주세요.`);
      return;
    }
    if (!isInitial) {
      if (subscription === '블랙') {
        if (!window.confirm('카테고리 변경 시 추가금 10만원 결제가 진행됩니다. 결제 후 변경하시겠습니까?')) return;
        alert('추가금 10만원 결제가 완료되었습니다. 이번 주기의 카테고리가 변경되었습니다.');
      } else if (subscription === '골드') {
        if (!window.confirm('카테고리를 변경하시겠습니까? (월 1회 제한, 추가금 없음)')) return;
        alert('카테고리가 성공적으로 변경되었습니다.');
      }
    }

    const newChangeCount = isInitial ? 0 : currentCategoryData.changeCount + 1;

    fetch(`${baseUrl}/api/competitor/categories`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        brandId: myBrandId,
        cycleKey: activeCycle.cycleKey,
        selectedCategories: tempCategorySelections,
        changeCount: newChangeCount
      })
    })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        setCategorySubData({
          selectedCategories: tempCategorySelections,
          changeCount: newChangeCount
        });
        setIsCategoryModalOpen(false);
      } else {
        alert(`저장 실패: ${data.message}`);
      }
    })
    .catch(err => {
      console.error('카테고리 저장 통신 에러:', err);
      alert('서버 통신 중 오류가 발생했습니다.');
    });
  };

  const filteredBrands = competitorBrands.filter(b => {
    const matchesInitial = matchInitialFilter(b.brand_name, selectedInitial);
    const matchesSearch = b.brand_name.toLowerCase().includes(searchTerm.toLowerCase().trim());
    return matchesInitial && matchesSearch;
  });
  
  const sortedBrands = [...filteredBrands].sort((a, b) => {
    if (sortOrder === 'asc') return a.brand_name.localeCompare(b.brand_name, 'ko');
    return b.brand_name.localeCompare(a.brand_name, 'ko');
  });

  const totalPages = Math.ceil(sortedBrands.length / itemsPerPage) || 1;
  const indexOfLastItem = currentPage * itemsPerPage;
  const indexOfFirstItem = indexOfLastItem - itemsPerPage;
  const currentBrands = sortedBrands.slice(indexOfFirstItem, indexOfLastItem);

  return (
    <div style={{ padding: '40px 20px', maxWidth: '1000px', margin: '0 auto', fontFamily: "'Pretendard', sans-serif" }}>
      
      <style>
        {`
          .product-card-hover {
            transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.25s cubic-bezier(0.16, 1, 0.3, 1);
          }
          .product-card-hover:hover {
            transform: translateY(-6px);
            box-shadow: 0 12px 24px rgba(0,0,0,0.08);
          }
        `}
      </style>

      {/* 상단 우측 '목록으로 돌아가기' 버튼 */}
      <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: '10px', minHeight: '30px' }}>
        {view === 'products' && (
          <button 
            onClick={handleBackToBrands} 
            style={{ 
              display: 'inline-flex', alignItems: 'center', gap: '8px', background: 'transparent', 
              color: '#555', border: 'none', fontSize: '1rem', cursor: 'pointer', padding: '0', fontWeight: '500' 
            }}
          >
            ← 브랜드 목록으로
          </button>
        )}
      </div>

      <header style={{ textAlign: 'center', marginBottom: '30px' }}>
        <h2 style={{ fontSize: '1.8rem', fontWeight: 'bold', color: '#111', marginBottom: '8px' }}>
          타사 브랜드 상품 분석
        </h2>
        <p style={{ color: '#666', fontSize: '1rem' }}>
          타사 브랜드 상품 분석 페이지 입니다. 조회할 브랜드, 상품을 선택해보세요.
        </p>
      </header>

      {/* 구독 현황 카드 */}
      <div style={{
        backgroundColor: '#fafafa', border: '1px solid #eee', borderRadius: '16px', padding: '24px 20px', marginBottom: '35px',
        display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '15px', boxShadow: '0 2px 8px rgba(0,0,0,0.02)'
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '12px', color: '#888', marginBottom: '8px', fontWeight: 'bold' }}>구독 플랜</div>
          <div style={{ fontSize: '15px', fontWeight: 'bold', color: '#111' }}>
            <span style={{ backgroundColor: subscription ? '#111' : '#64748b', color: '#fff', padding: '3px 10px', borderRadius: '12px', fontSize: '12px', marginRight: '6px' }}>
              {subscription || '미구독'}
            </span>
            올리뷰 플랜
          </div>
        </div>

        {currentPlan.type === 'category' ? (
          <>
            <div style={{ textAlign: 'center', borderLeft: '1px solid #eaeaea' }}>
              <div style={{ fontSize: '12px', color: '#888', marginBottom: '8px', fontWeight: 'bold' }}>지정 카테고리</div>
              <div style={{ fontSize: '14px', fontWeight: 'bold', color: '#2563eb' }}>
                {currentCategoryData.selectedCategories.length > 0 
                  ? currentCategoryData.selectedCategories.map(c => c.name).join(', ')
                  : '미선택'}
              </div>
            </div>

            <div style={{ textAlign: 'center', borderLeft: '1px solid #eaeaea' }}>
              <div style={{ fontSize: '12px', color: '#888', marginBottom: '8px', fontWeight: 'bold' }}>월 변경 사용 횟수</div>
              <div style={{ fontSize: '15px', fontWeight: 'bold', color: '#111' }}>
                {currentCategoryData.changeCount} / 1회
                <span style={{ fontSize: '11px', color: subscription === '블랙' ? '#dc2626' : '#10b981', display: 'block', fontWeight: 'normal', marginTop: '2px' }}>
                  {subscription === '블랙' ? '(변경 시 10만원)' : '(변경 시 무료)'}
                </span>
              </div>
            </div>

            <div style={{ textAlign: 'center', borderLeft: '1px solid #eaeaea', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center' }}>
              <button 
                onClick={handleOpenCategoryModal}
                style={{
                  backgroundColor: '#111', color: '#fff', border: 'none', borderRadius: '8px', padding: '8px 14px',
                  fontSize: '0.85rem', fontWeight: 'bold', cursor: 'pointer'
                }}
              >
                {currentCategoryData.selectedCategories.length === 0 ? '카테고리 선택' : '카테고리 변경'}
              </button>
            </div>
          </>
        ) : (
          <>
            <div style={{ textAlign: 'center', borderLeft: '1px solid #eaeaea' }}>
              <div style={{ fontSize: '12px', color: '#888', marginBottom: '8px', fontWeight: 'bold' }}>제공 열람 수</div>
              <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#333' }}>
                {subscription ? `${currentPlan.total}개` : '-'}
              </div>
            </div>

            <div 
              onClick={() => currentViews.length > 0 && setIsModalOpen(true)}
              style={{ textAlign: 'center', borderLeft: '1px solid #eaeaea', cursor: currentViews.length > 0 ? 'pointer' : 'default' }}
            >
              <div style={{ fontSize: '12px', color: '#888', marginBottom: '8px', fontWeight: 'bold' }}>
                차감 열람 수 {currentViews.length > 0 && <span style={{ fontSize: '11px', color: '#2563eb' }}>🔍</span>}
              </div>
              <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#2563eb', textDecoration: currentViews.length > 0 ? 'underline' : 'none' }}>
                {subscription ? `${usedCount}개` : '-'}
                {hasGreenFreeBenefit && (
                  <span style={{ fontSize: '11px', color: '#10b981', display: 'block', fontWeight: 'normal', marginTop: '2px' }}>
                    (전월 재열람 1개 미차감)
                  </span>
                )}
              </div>
            </div>

            <div style={{ textAlign: 'center', borderLeft: '1px solid #eaeaea' }}>
              <div style={{ fontSize: '12px', color: '#888', marginBottom: '8px', fontWeight: 'bold' }}>잔여 열람 수</div>
              <div style={{ fontSize: '16px', fontWeight: 'bold', color: typeof remaining === 'number' && remaining <= 1 ? '#dc2626' : '#10b981' }}>
                {subscription ? `${remaining}개` : '-'}
              </div>
            </div>
          </>
        )}
      </div>

      {view === 'brands' ? (
        <div>
          {!subscription && (
            <div style={{ backgroundColor: '#fffbeb', border: '1px solid #fde68a', padding: '16px', borderRadius: '12px', textAlign: 'center', marginBottom: '25px', color: '#92400e', fontSize: '0.95rem' }}>
              ⚠️ 현재 미구독 상태이므로 타사 브랜드 상품 열람이 제한됩니다. <button onClick={() => onNavigate('subscription')} style={{ marginLeft: '10px', padding: '6px 12px', backgroundColor: '#d97706', color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 'bold', cursor: 'pointer' }}>구독하러 가기</button>
            </div>
          )}

          <div style={{ backgroundColor: '#f8f9fa', border: '1px solid #e9ecef', borderRadius: '12px', padding: '20px', marginBottom: '25px' }}>
            <div style={{ position: 'relative', marginBottom: '16px' }}>
              <input 
                type="text" value={searchTerm} onChange={(e) => { setSearchTerm(e.target.value); setCurrentPage(1); }}
                placeholder="찾으시는 타사 브랜드명을 입력하세요 (예: 클리오, 롬앤)"
                style={{ width: '70%', padding: '12px 40px 12px 16px', fontSize: '0.95rem', borderRadius: '8px', border: '1px solid #ddd', outline: 'none', boxSizing: 'border-box' }}
              />
              {searchTerm && (
                <button onClick={() => { setSearchTerm(''); setCurrentPage(1); }} style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', fontSize: '1rem', color: '#999', cursor: 'pointer' }}>✕</button>
              )}
            </div>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '10px' }}>
              {koreanInitials.map((item) => (
                <button key={item} onClick={() => { setSelectedInitial(item); setCurrentPage(1); }} style={{ padding: '4px 10px', borderRadius: '6px', border: '1px solid', borderColor: selectedInitial === item ? '#111' : '#e0e0e0', backgroundColor: selectedInitial === item ? '#111' : '#fff', color: selectedInitial === item ? '#fff' : '#444', fontWeight: selectedInitial === item ? 'bold' : 'normal', fontSize: '0.85rem', cursor: 'pointer' }}>{item}</button>
              ))}
            </div>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
              {englishAlphabets.map((item) => (
                <button key={item} onClick={() => { setSelectedInitial(item); setCurrentPage(1); }} style={{ padding: '3px 8px', borderRadius: '4px', border: '1px solid', borderColor: selectedInitial === item ? '#111' : '#e0e0e0', backgroundColor: selectedInitial === item ? '#111' : '#fff', color: selectedInitial === item ? '#fff' : '#666', fontWeight: selectedInitial === item ? 'bold' : 'normal', fontSize: '0.8rem', cursor: 'pointer' }}>{item}</button>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <h2 style={{ fontSize: '1.2rem', margin: 0, fontWeight: 'bold', color: '#333' }}>
              타사 브랜드 목록 <span style={{ fontSize: '0.9rem', color: '#888', fontWeight: 'normal' }}>({sortedBrands.length}개)</span>
            </h2>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button onClick={() => { setSortOrder('asc'); setCurrentPage(1); }} style={{ padding: '6px 14px', borderRadius: '20px', border: '1px solid #ddd', backgroundColor: sortOrder === 'asc' ? '#111' : '#fff', color: sortOrder === 'asc' ? '#fff' : '#555', fontWeight: '500', cursor: 'pointer', fontSize: '0.85rem' }}>가나다순</button>
              <button onClick={() => { setSortOrder('desc'); setCurrentPage(1); }} style={{ padding: '6px 14px', borderRadius: '20px', border: '1px solid #ddd', backgroundColor: sortOrder === 'desc' ? '#111' : '#fff', color: sortOrder === 'desc' ? '#fff' : '#555', fontWeight: '500', cursor: 'pointer', fontSize: '0.85rem' }}>역가나다순</button>
            </div>
          </div>

          {currentBrands.length > 0 ? (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
                {currentBrands.map((brand) => (
                  <div 
                    key={brand.brand_id} onClick={() => handleBrandClick(brand)}
                    className="product-card-hover"
                    style={{ height: '110px', backgroundColor: '#fff', borderRadius: '12px', display: 'flex', justifyContent: 'center', alignItems: 'center', textAlign: 'center', padding: '15px', cursor: 'pointer', fontSize: '1.05rem', fontWeight: 'bold', color: '#333', border: '1px solid #eee', boxShadow: '0 2px 5px rgba(0,0,0,0.02)' }}
                  >
                    {brand.brand_name}
                  </div>
                ))}
              </div>

              {/* 🌟 페이지네이션 UI (처음 / 이전 / 번호 / 다음 / 맨끝) */}
              {totalPages > 1 && (
                <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '6px', marginTop: '35px' }}>
                  {/* 처음 버튼 */}
                  <button
                    onClick={() => { setCurrentPage(1); window.scrollTo(0, 300); }}
                    disabled={currentPage === 1}
                    style={{
                      padding: '8px 12px', borderRadius: '8px', border: '1px solid #cbd5e1',
                      backgroundColor: currentPage === 1 ? '#f8fafc' : '#fff',
                      color: currentPage === 1 ? '#94a3b8' : '#333',
                      cursor: currentPage === 1 ? 'not-allowed' : 'pointer', fontSize: '0.85rem', fontWeight: '500'
                    }}
                  >
                    처음
                  </button>

                  {/* 이전 버튼 */}
                  <button
                    onClick={() => { setCurrentPage(prev => Math.max(prev - 1, 1)); window.scrollTo(0, 300); }}
                    disabled={currentPage === 1}
                    style={{
                      padding: '8px 12px', borderRadius: '8px', border: '1px solid #cbd5e1',
                      backgroundColor: currentPage === 1 ? '#f8fafc' : '#fff',
                      color: currentPage === 1 ? '#94a3b8' : '#333',
                      cursor: currentPage === 1 ? 'not-allowed' : 'pointer', fontSize: '0.85rem', fontWeight: '500'
                    }}
                  >
                    이전
                  </button>

                  {/* 페이지 번호 목록 */}
                  {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    let pageNum;
                    if (totalPages <= 5) {
                      pageNum = i + 1;
                    } else if (currentPage <= 3) {
                      pageNum = i + 1;
                    } else if (currentPage >= totalPages - 2) {
                      pageNum = totalPages - 4 + i;
                    } else {
                      pageNum = currentPage - 2 + i;
                    }

                    return (
                      <button
                        key={pageNum}
                        onClick={() => { setCurrentPage(pageNum); window.scrollTo(0, 300); }}
                        style={{
                          minWidth: '36px', height: '36px', padding: '0 8px', borderRadius: '8px',
                          border: currentPage === pageNum ? '1px solid #111' : '1px solid #cbd5e1',
                          backgroundColor: currentPage === pageNum ? '#111' : '#fff',
                          color: currentPage === pageNum ? '#fff' : '#333',
                          fontWeight: currentPage === pageNum ? 'bold' : 'normal',
                          cursor: 'pointer', fontSize: '0.9rem'
                        }}
                      >
                        {pageNum}
                      </button>
                    );
                  })}

                  {/* 다음 버튼 */}
                  <button
                    onClick={() => { setCurrentPage(prev => Math.min(prev + 1, totalPages)); window.scrollTo(0, 300); }}
                    disabled={currentPage === totalPages}
                    style={{
                      padding: '8px 12px', borderRadius: '8px', border: '1px solid #cbd5e1',
                      backgroundColor: currentPage === totalPages ? '#f8fafc' : '#fff',
                      color: currentPage === totalPages ? '#94a3b8' : '#333',
                      cursor: currentPage === totalPages ? 'not-allowed' : 'pointer', fontSize: '0.85rem', fontWeight: '500'
                    }}
                  >
                    다음
                  </button>

                  {/* 맨끝 버튼 */}
                  <button
                    onClick={() => { setCurrentPage(totalPages); window.scrollTo(0, 300); }}
                    disabled={currentPage === totalPages}
                    style={{
                      padding: '8px 12px', borderRadius: '8px', border: '1px solid #cbd5e1',
                      backgroundColor: currentPage === totalPages ? '#f8fafc' : '#fff',
                      color: currentPage === totalPages ? '#94a3b8' : '#333',
                      cursor: currentPage === totalPages ? 'not-allowed' : 'pointer', fontSize: '0.85rem', fontWeight: '500'
                    }}
                  >
                    맨끝
                  </button>
                </div>
              )}
            </>
          ) : (
            <div style={{ textAlign: 'center', padding: '60px 0', color: '#888' }}>해당 조건에 맞는 브랜드가 없습니다.</div>
          )}
        </div>
      ) : (
        <div>
          <div style={{ textAlign: 'center', marginBottom: '30px' }}>
            <h2 style={{ fontSize: '1.8rem', margin: 0, fontWeight: 'bold', color: '#111' }}>{selectedBrand?.brand_name} 상품 목록</h2>
          </div>

          <div style={{ display: 'flex', justifyContent: 'center', gap: '15px', marginBottom: '35px' }}>
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

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px' }}>
            {products.length > 0 ? (
              products.map((product) => (
                <div 
                  key={product.product_id} 
                  onClick={() => handleProductClick(product)} 
                  className="product-card-hover"
                  style={{ backgroundColor: '#fff', borderRadius: '12px', overflow: 'hidden', cursor: 'pointer', border: '1px solid #eee', position: 'relative' }}
                >
                  <div style={{ width: '100%', aspectRatio: '1/1', backgroundColor: '#fdfdfd', borderBottom: '1px solid #eee', position: 'relative' }}>
                    {product.product_image_url ? (
                      <img src={product.product_image_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : (
                      <div style={{ width: '100%', height: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', color: '#ccc', fontSize: '0.85rem' }}>No Image</div>
                    )}
                  </div>
                  <div style={{ padding: '14px', textAlign: 'left' }}>
                    <div style={{ fontSize: '12px', color: '#888', fontWeight: 'bold', marginBottom: '4px' }}>{selectedBrand?.brand_name}</div>
                    <div style={{ fontSize: '14px', fontWeight: '500', color: '#222', lineHeight: '1.4' }}>{product.product_name}</div>
                  </div>
                </div>
              ))
            ) : (
              <p style={{ gridColumn: 'span 4', textAlign: 'center', color: '#888', padding: '60px 0' }}>해당 카테고리에 등록된 상품이 없습니다.</p>
            )}
          </div>
        </div>
      )}

      {isCategoryModalOpen && (
        <div style={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000 }}>
          <div style={{ backgroundColor: '#fff', borderRadius: '16px', padding: '24px', maxWidth: '440px', width: '90%', boxShadow: '0 10px 25px rgba(0,0,0,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 'bold', color: '#111' }}>
                {subscription} 플랜 카테고리 선택 ({tempCategorySelections.length}/{currentPlan.maxCategories}개)
              </h3>
              <button onClick={() => setIsCategoryModalOpen(false)} style={{ background: 'none', border: 'none', fontSize: '1.2rem', cursor: 'pointer', color: '#666' }}>✕</button>
            </div>

            <p style={{ fontSize: '0.85rem', color: '#666', marginBottom: '20px', lineHeight: '1.4' }}>
              선택하신 카테고리 안의 타사 상품은 이번 구독 주기 동안 무제한 열람 가능합니다.
              {subscription === '블랙' && <strong style={{ color: '#dc2626', display: 'block', marginTop: '4px' }}>* 카테고리 변경 시 10만원의 추가 결제가 진행됩니다. (월 1회 제한)</strong>}
              {subscription === '골드' && <strong style={{ color: '#10b981', display: 'block', marginTop: '4px' }}>* 카테고리 변경 시 추가 비용이 발생하지 않습니다. (월 1회 제한)</strong>}
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px', marginBottom: '24px' }}>
              {allMainCategories.map((cat) => {
                const isSelected = tempCategorySelections.some(c => c.id === cat.category_id);
                return (
                  <button
                    key={cat.category_id}
                    onClick={() => handleToggleCategorySelect(cat)}
                    style={{
                      padding: '12px', borderRadius: '8px', border: '1px solid',
                      borderColor: isSelected ? '#2563eb' : '#ddd',
                      backgroundColor: isSelected ? '#eff6ff' : '#fff',
                      color: isSelected ? '#2563eb' : '#333',
                      fontWeight: isSelected ? 'bold' : 'normal',
                      cursor: 'pointer', textAlign: 'center'
                    }}
                  >
                    {cat.category_name} {isSelected && '✓'}
                  </button>
                );
              })}
            </div>

            <button
              onClick={handleSaveCategorySelection}
              style={{
                width: '100%', padding: '12px', backgroundColor: '#111', color: '#fff', border: 'none',
                borderRadius: '8px', fontWeight: 'bold', fontSize: '0.95rem', cursor: 'pointer'
              }}
            >
              선택 완료 및 적용
            </button>
          </div>
        </div>
      )}

      {isModalOpen && (
        <div style={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000 }}>
          <div style={{ backgroundColor: '#fff', borderRadius: '16px', padding: '24px', maxWidth: '480px', width: '90%', maxHeight: '70vh', overflowY: 'auto', boxShadow: '0 10px 25px rgba(0,0,0,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 'bold', color: '#111' }}>
                이번 주기 열람 상품 ({currentViews.length}개)
              </h3>
              <button onClick={() => setIsModalOpen(false)} style={{ background: 'none', border: 'none', fontSize: '1.2rem', cursor: 'pointer', color: '#666' }}>✕</button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {currentViews.map((item, idx) => (
                <div key={idx} onClick={() => {
                  const targetProduct = item.fullProduct || { product_id: item.id, product_name: item.name, product_image_url: item.imageUrl };
                  // 🌟 localStorage -> sessionStorage로 변경
                  sessionStorage.setItem('oliview_selectedCompetitorProduct', JSON.stringify(targetProduct));
                  setIsModalOpen(false);
                  onNavigate('competitorProductDetail');
                }} style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '10px', border: '1px solid #eee', borderRadius: '8px', cursor: 'pointer' }}>
                  <div style={{ width: '48px', height: '48px', backgroundColor: '#f9f9f9', borderRadius: '6px', overflow: 'hidden', flexShrink: 0 }}>
                    {item.imageUrl ? <img src={item.imageUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : <div style={{ fontSize: '10px', color: '#ccc', textAlign: 'center', lineHeight: '48px' }}>No Img</div>}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '11px', color: '#888', fontWeight: 'bold' }}>{item.brandName}</div>
                    <div style={{ fontSize: '13px', fontWeight: '500', color: '#222' }}>{item.name}</div>
                  </div>
                  <div style={{ fontSize: '12px', color: '#2563eb', fontWeight: 'bold' }}>보기 →</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default CompetitorDashboardPage;