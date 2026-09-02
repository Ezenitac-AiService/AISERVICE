import React, { useState, useEffect } from 'react';
import MainPage from './MainPage';
import LoginPage from './LoginPage';
import TermsPage from './TermsPage';
import RegisterPage from './RegisterPage';
import ProductDetailPage from './ProductDetailPage';
import SubscriptionPage from './SubscriptionPage';
import CompetitorDashboardPage from './CompetitorDashboardPage';
import CompetitorProductDetailPage from './CompetitorProductDetailPage';
import MyBrandPage from './MyBrandpage'; 
import MySubscriptionPage from './MySubscriptionPage';
import './App.css';
import BrandInfoPage from './BrandInfoPage';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/bteam/oliview';

function App() {
  const [currentPage, setCurrentPage] = useState(() => {
    const isLoggedIn = sessionStorage.getItem('oliview_isLoggedIn') === 'true';
    const savedPage = sessionStorage.getItem('oliview_currentPage');
    const savedProductId = sessionStorage.getItem('oliview_selectedProduct_id');

    if (!isLoggedIn || savedPage === 'login') {
      return 'main';
    }

    if (savedPage === 'productDetail' && savedProductId) {
      return 'productDetail';
    }
    return savedPage || 'main';
  });
  
  const [subscription, setSubscription] = useState(null);
  const [nextBillingDate, setNextBillingDate] = useState(null);
  const [isCancelled, setIsCancelled] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(() => sessionStorage.getItem('oliview_isLoggedIn') === 'true');
  const [user, setUser] = useState(() => {
    try {
      const savedUser = sessionStorage.getItem('oliview_user');
      return savedUser ? JSON.parse(savedUser) : null;
    } catch {
      return null;
    }
  });
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);

  const refreshUserStatus = () => {
    const storedUser = JSON.parse(sessionStorage.getItem('oliview_user'));
    const brandId = storedUser?.brandId || storedUser?.brand_id || user?.brandId;
    if (!brandId) return;
    
    fetch(`${API_BASE_URL}/api/user/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ brandId: brandId })
    })
    .then(res => res.json())
    .then(data => {
      if (data.success && data.isLoggedIn) {
        const updatedUser = {
          ...storedUser,
          subscription: data.subscription
        };
        setUser(updatedUser);
        sessionStorage.setItem('oliview_user', JSON.stringify(updatedUser));

        setSubscription(data.subscription?.planName || null);
        setNextBillingDate(data.subscription?.nextBillingDate || null);
      }
    })
    .catch(err => console.error("상태 갱신 실패:", err));
  };

  useEffect(() => {
    const savedUser = sessionStorage.getItem('oliview_user');
    
    if (savedUser) {
      try {
        const parsedUser = JSON.parse(savedUser);
        const brandId = parsedUser.brandId || parsedUser.brand_id;

        if (brandId) {
          fetch(`${API_BASE_URL}/api/user/status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ brandId: brandId })
          })
          .then(res => res.json())
          .then(data => {
            if (data.success && data.isLoggedIn) {
              setIsLoggedIn(true);
              setUser(parsedUser);
              setSubscription(data.subscription?.planName || null); 
              setNextBillingDate(data.subscription?.nextBillingDate || null);
              setIsCancelled(data.isCancelled || false);
            } else {
              handleLogoutQuiet();
            }
          })
          .catch(err => {
            console.error("서버 상태 검증 실패:", err);
            handleLogoutQuiet();
          })
          .finally(() => {
            setIsCheckingAuth(false);
          });
          return;
        }
      } catch (e) {
        console.error("저장된 유저 정보 파싱 실패", e);
      }
    }
    
    handleLogoutQuiet();
    setIsCheckingAuth(false);
  }, []);

  const handleLogoutQuiet = () => {
    sessionStorage.removeItem('oliview_isLoggedIn');
    sessionStorage.removeItem('oliview_user');
    sessionStorage.removeItem('oliview_subscription');
    sessionStorage.removeItem('oliview_isCancelled');
    sessionStorage.removeItem('oliview_selectedProduct_id');
    setIsLoggedIn(false);
    setUser(null);
    setSubscription(null);
    setNextBillingDate(null);
    setIsCancelled(false);
  };

  useEffect(() => {
    sessionStorage.setItem('oliview_currentPage', currentPage);
    if (isLoggedIn) {
      refreshUserStatus();
    }
  }, [currentPage, isLoggedIn]);

  const navigateTo = (page) => {
    if (page === 'main_logout') {
      handleLogoutQuiet();
      setCurrentPage('main');
    } else {
      if (page === 'myBrand' || page === 'main') {
        sessionStorage.removeItem('oliview_selectedProduct_id');
        sessionStorage.removeItem('oliview_selectedProduct');
        sessionStorage.removeItem('oliview_myBrand_selectedProductId');
      }
      setCurrentPage(page);
    }
    window.scrollTo(0, 0);
  };

  const leftNavBtnStyle = (pageName) => {
    const isActive = currentPage === pageName;
    return {
      width: '100%',
      padding: '12px 16px',
      backgroundColor: isActive ? '#f1f5f9' : 'transparent',
      border: 'none',
      borderRadius: '8px',
      cursor: 'pointer',
      fontSize: '14px',
      fontWeight: isActive ? '700' : '600',
      color: isActive ? '#0f172a' : '#64748b',
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      textAlign: 'left',
      transition: 'all 0.15s ease-in-out'
    };
  };

  const rightNavBtnStyle = {
    width: '100%', 
    height: '48px', 
    backgroundColor: '#f8fafc', 
    border: '1px solid #e2e8f0', 
    borderRadius: '8px', 
    cursor: 'pointer', 
    fontSize: '13px', 
    fontWeight: '600', 
    color: '#475569',
    display: 'flex', 
    flexDirection: 'row', 
    justifyContent: 'center', 
    alignItems: 'center', 
    gap: '8px', 
    transition: 'all 0.2s ease-in-out'
  };

  if (isCheckingAuth) {
    return <div style={{ textAlign: 'center', padding: '100px', fontSize: '18px' }}>보안 인증 확인 중...</div>;
  }

  return (
    <div className="App" style={{ backgroundColor: '#ffffff', minHeight: '100vh', width: '100%', overflowX: 'auto' }}>
      <div style={{
        width: '1280px',
        minWidth: '1280px',
        margin: '0 auto',
        display: 'flex',
        alignItems: 'stretch',
        minHeight: '100vh'
      }}>

        {/* 👈 [좌측 메뉴 영역] */}
        <aside style={{
          width: '220px',
          flexShrink: 0,
          padding: '24px 16px'
        }}>
          <div style={{
            position: 'sticky',
            top: '20px',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px'
          }}>
          
            {/* 좌측 프로필 및 로그인 정보 카드 */}
            <div style={{
              padding: '12px 4px 16px 4px',
              borderBottom: '1px solid #ebeef3',
              marginBottom: '12px',
              textAlign: 'left'
            }}>
              {isLoggedIn ? (
                <>
                  <div style={{ fontWeight: '700', fontSize: '16px', color: '#111', marginBottom: '4px' }}>
                    {user?.brandName || '브랜드명'}
                  </div>

                  <div style={{ fontSize: '13px', color: '#475569', marginBottom: '8px', lineHeight: '1.4', wordBreak: 'keep-all' }}>
                    담당자 <strong>{user?.managerName || '담당자'}</strong>님 환영합니다.
                  </div>

                  <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '14px', lineHeight: '1.4' }}>
                    <span style={{ fontWeight: '700', color: subscription ? '#15803d' : '#ef4444' }}>
                      {subscription ? `${subscription} 올리뷰` : '미구독'}
                    </span>
                    {nextBillingDate && subscription && (
                      <span style={{ color: '#64748b' }}> / ~{nextBillingDate}</span>
                    )}
                  </div>

                  <button 
                    onClick={() => navigateTo('main_logout')} 
                    style={{ 
                      width: '100%', 
                      padding: '8px', 
                      backgroundColor: '#f8fafc', 
                      border: '1px solid #e2e8f0', 
                      borderRadius: '6px', 
                      fontSize: '13px', 
                      cursor: 'pointer', 
                      fontWeight: '600', 
                      color: '#64748b' 
                    }}
                  >
                    로그아웃
                  </button>
                </>
              ) : (
                <>
                  <div style={{ fontSize: '13px', color: '#666', marginBottom: '12px', textAlign: 'left' }}>
                    로그인을 해주세요.
                  </div>
                  <button 
                    onClick={() => navigateTo('login')} 
                    style={{ 
                      width: '100%', 
                      padding: '8px', 
                      backgroundColor: '#111', 
                      border: 'none', 
                      borderRadius: '6px', 
                      fontSize: '13px', 
                      cursor: 'pointer', 
                      fontWeight: 'bold', 
                      color: '#fff' 
                    }}
                  >
                    로그인
                  </button>
                </>
              )}
            </div>

            {/* 🌟 중복되던 아래의 1px 경계선 div를 삭제했습니다. */}
            
            <button onClick={() => navigateTo('main')} style={leftNavBtnStyle('main')} title="홈">
              <span>홈</span>
            </button>
            <button onClick={() => { if (isLoggedIn) navigateTo('dashboard_member'); else { alert('로그인이 필요합니다.'); navigateTo('login'); } }} style={leftNavBtnStyle('dashboard_member')} title="회원정보">
              <span>회원정보</span>
            </button>
            <button onClick={() => { if (isLoggedIn) navigateTo('mySubscription'); else { alert('로그인이 필요합니다.'); navigateTo('login'); } }} style={leftNavBtnStyle('mySubscription')} title="구독정보">
              <span>구독정보</span>
            </button>
            <button onClick={() => { if (isLoggedIn) navigateTo('myBrand'); else { alert('로그인이 필요합니다.'); navigateTo('login'); } }} style={leftNavBtnStyle('myBrand')} title="내브랜드">
              <span>내 브랜드</span>
            </button>
            <button onClick={() => { if (isLoggedIn) navigateTo('competitorDashboard'); else { alert('로그인이 필요합니다.'); navigateTo('login'); } }} style={leftNavBtnStyle('competitorDashboard')} title="타사브랜드">
              <span>타사 브랜드</span>
            </button>

            <button onClick={() => window.open('/bteam/chatb', '_blank')} style={rightNavBtnStyle} title="올원쳇">
              <span style={{ fontSize: '16px' }}>🤖</span>
              <span>올원쳇</span>
            </button>

            <button onClick={() => window.open('/bteam/chata', '_blank')} style={rightNavBtnStyle} title="올리쳇">
              <span style={{ fontSize: '16px' }}>🤖</span>
              <span>올리쳇</span>
            </button>

            <button onClick={() => window.open('https://www.oliveyoung.co.kr', '_blank')} style={rightNavBtnStyle} title="올리브영">
              <span style={{ fontSize: '16px' }}>🌱</span>
              <span>올리브영</span>
            </button>
          </div>
        </aside>

        {/* 📄 [중앙 본문 영역] */}
        <main style={{
          flex: 1,
          minWidth: 0,
          padding: '24px 32px',
        }}>
          {currentPage === 'main' && <MainPage onNavigate={navigateTo} isLoggedIn={isLoggedIn} subscription={subscription} apiBaseUrl={API_BASE_URL} />}
          {currentPage === 'login' && <LoginPage onNavigate={navigateTo} setIsLoggedIn={setIsLoggedIn} setUser={setUser} refreshUserStatus={refreshUserStatus} apiBaseUrl={API_BASE_URL} />}
          {currentPage === 'terms' && <TermsPage onNavigate={navigateTo} />}
          {currentPage === 'register' && <RegisterPage onNavigate={navigateTo} apiBaseUrl={API_BASE_URL} />}
          {currentPage === 'dashboard_member' && (
            <BrandInfoPage user={user} apiBaseUrl={API_BASE_URL} onNavigate={navigateTo} />
          )}
          {currentPage === 'productDetail' && (
            <ProductDetailPage onNavigate={navigateTo} subscription={subscription} apiBaseUrl={API_BASE_URL} />
          )}
          {currentPage === 'subscription' && (
            <SubscriptionPage onNavigate={navigateTo} setSubscription={setSubscription} setIsCancelled={setIsCancelled} user={user} apiBaseUrl={API_BASE_URL} refreshUserStatus={refreshUserStatus} />
          )}
          {currentPage === 'competitorDashboard' && (
            <CompetitorDashboardPage onNavigate={navigateTo} subscription={subscription} setSubscription={setSubscription} user={user} apiBaseUrl={API_BASE_URL} />
          )}
          {currentPage === 'competitorProductDetail' && (
            <CompetitorProductDetailPage onNavigate={navigateTo} subscription={subscription} user={user} apiBaseUrl={API_BASE_URL} />
          )}
          {currentPage === 'mySubscription' && (
            <MySubscriptionPage onNavigate={navigateTo} user={user} apiBaseUrl={API_BASE_URL} refreshUserStatus={refreshUserStatus} />
          )}
          {currentPage === 'myBrand' && (
            user ? (
              <MyBrandPage user={user} onNavigate={navigateTo} apiBaseUrl={API_BASE_URL} />
            ) : (
              <div style={{ padding: '80px 0', textAlign: 'center' }}>
                <h2>로그인이 필요한 서비스입니다.</h2>
                <p style={{ color: '#666', marginTop: '8px' }}>유저 정보가 존재하지 않습니다.</p>
                <button 
                  onClick={() => navigateTo('login')}
                  style={{ padding: '10px 20px', marginTop: '20px', cursor: 'pointer', borderRadius: '6px', border: '1px solid #ccc', backgroundColor: '#fff' }}
                >
                  로그인 하러 가기
                </button>
              </div>
            )
          )}
        </main>

      </div>
    </div>
  );
}

export default App;