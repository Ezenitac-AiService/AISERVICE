import React from 'react';

function TermsPage({ onNavigate }) {
  return (
    <div style={{ padding: '100px', textAlign: 'center', fontFamily: 'sans-serif', display: 'flex', flexDirection: 'column', alignItems: 'center', minHeight: '80vh' }}>
      <h1 style={{ fontSize: '2.5rem', fontWeight: 'bold', marginBottom: '20px' }}>REGISTER</h1>
      
      <div style={{ marginBottom: 'auto', marginTop: '30px' }}>
        <p style={{ fontSize: '1.1rem', lineHeight: '1.6', fontWeight: 'bold' }}>
          상품개선 서비스 올리뷰를 이용하기 위해서는<br/>
          올리브영 입점 브랜드 고객님은<br/>
          브랜드 이름 가입 및 담당자 등록을 해주셔야 합니다.
        </p>
        <p style={{ fontSize: '1.1rem', marginTop: '30px' }}>
          아래 약관을 확인하시고 회원가입 해주세요.
        </p>
      </div>

      <button 
        onClick={() => onNavigate('register')} 
        style={{ padding: '15px 40px', backgroundColor: '#111', color: '#fff', border: 'none', borderRadius: '30px', cursor: 'pointer', fontWeight: 'bold', fontSize: '1.1rem', marginTop: '50px' }}
      >
        약관 동의 및 회원가입
      </button>

      <button onClick={() => onNavigate('login')} style={{ marginTop: '30px', padding: '10px 20px', border: 'none', background: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
        뒤로 가기
      </button>
    </div>
  );
}

export default TermsPage;