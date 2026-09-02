import React, { useState, useEffect } from 'react';

function BrandInfoPage({ user, apiBaseUrl, onNavigate }) {
  // 🌟 localStorage -> sessionStorage로 변경
  const brandId = user?.brandId || JSON.parse(sessionStorage.getItem('oliview_user'))?.brandId;
  const baseUrl = apiBaseUrl || '';

  const [currentBrandPw, setCurrentBrandPw] = useState('');
  const [newBrandPw, setNewBrandPw] = useState('');
  const [showCurrentPw, setShowCurrentPw] = useState(false);
  const [showNewPw, setShowNewPw] = useState(false);
  const [managers, setManagers] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  const [showWithdrawModal, setShowWithdrawModal] = useState(false);
  const [withdrawPw, setWithdrawPw] = useState('');
  const [agreeWithdrawTerms, setAgreeWithdrawTerms] = useState(false);
  const [isWithdrawing, setIsWithdrawing] = useState(false);

  useEffect(() => {
    if (brandId) {
      fetch(`${baseUrl}/api/brand-info/${brandId}`)
        .then(res => res.json())
        .then(data => {
          if (data.success) {
            const formatted = (data.managers || []).map(m => ({
              ...m,
              originalName: m.name || '',
              originalEmail: m.email || '',
              name: m.name || '',
              email: m.email || '',
              managerPw: '',
              isEditing: false,
              authCode: '',
              isEmailSent: false,
              isVerified: true
            }));
            setManagers(formatted);
          }
          setIsLoading(false);
        })
        .catch(err => {
          console.error("회원정보 조회 실패:", err);
          setIsLoading(false);
        });
    }
  }, [brandId, baseUrl]);

  // 담당자 정보 입력 변경 핸들러
  const handleManagerChange = (index, field, value) => {
    const updated = [...managers];
    let sanitizedValue = value;

    if (field === 'name') {
      sanitizedValue = value.replace(/[^ㄱ-ㅎㅏ-ㅣ가-힣a-zA-Z]/g, '');
    } else if (field === 'managerPw') {
      sanitizedValue = value.replace(/[ㄱ-ㅎㅏ-ㅣ가-힣]/g, '');
    }

    updated[index][field] = sanitizedValue;

    // 이메일 변경 시 인증 상태 리셋
    if (field === 'email') {
      if (sanitizedValue !== updated[index].originalEmail) {
        updated[index].isVerified = false;
        updated[index].isEmailSent = false;
        updated[index].authCode = '';
      } else {
        updated[index].isVerified = true;
        updated[index].isEmailSent = false;
        updated[index].authCode = '';
      }
    }

    setManagers(updated);
  };

  // 수정 모드 토글 (정보 수정 / 수정 취소)
  const toggleEditManager = (index) => {
    const updated = [...managers];
    const target = updated[index];

    if (target.isEditing) {
      // 🌟 새로 추가한 담당자(DB에 manager_id가 없는 경우)는 취소 클릭 시 창 삭제
      if (!target.manager_id) {
        updated.splice(index, 1);
        setManagers(updated);
        return;
      }

      // 기존 저장되어 있던 담당자는 원래 정보로 복원
      target.name = target.originalName;
      target.email = target.originalEmail;
      target.managerPw = '';
      target.authCode = '';
      target.isEmailSent = false;
      target.isVerified = true;
      target.isEditing = false;
    } else {
      target.isEditing = true;
    }

    setManagers(updated);
  };

  // 신규 담당자 추가
  const handleAddManager = () => {
    if (managers.length >= 2) return;
    setManagers([
      ...managers,
      {
        name: '',
        email: '',
        originalName: '',
        originalEmail: '',
        managerPw: '',
        is_active: 1,
        isEditing: true,
        authCode: '',
        isEmailSent: false,
        isVerified: false
      }
    ]);
  };

  // 이메일 인증번호 발송
  const sendAuthCode = async (index) => {
    const email = managers[index].email;
    if (!email) return alert('이메일을 입력해 주세요.');

    try {
      const checkRes = await fetch(`${baseUrl}/api/check-email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, currentBrandId: brandId })
      });
      const checkData = await checkRes.json();

      if (checkData.isDuplicate) {
        alert('이미 다른 계정에서 사용 중인 이메일입니다.');
        return;
      }

      const res = await fetch(`${baseUrl}/api/send-auth-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      const data = await res.json();
      alert(data.message);

      if (data.success) {
        const updated = [...managers];
        updated[index].isEmailSent = true;
        setManagers(updated);
      }
    } catch (e) {
      alert('인증번호 발송 실패');
    }
  };

  // 이메일 인증번호 검증
  const verifyAuthCode = async (index) => {
    const { email, authCode } = managers[index];
    if (!authCode) return alert('인증번호를 입력해 주세요.');

    try {
      const res = await fetch(`${baseUrl}/api/verify-auth-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, code: authCode })
      });
      const data = await res.json();

      if (data.success) {
        alert('이메일 인증이 완료되었습니다.');
        const updated = [...managers];
        updated[index].isVerified = true;
        setManagers(updated);
      } else {
        alert(data.message);
      }
    } catch (e) {
      alert('인증 실패');
    }
  };

  // 회원정보 저장 제출
  const handleUpdateInfo = (e) => {
    e.preventDefault();
    if (!currentBrandPw) {
      alert("정보 수정을 위해 기존 브랜드 비밀번호를 입력해 주세요.");
      return;
    }

    // 변경된 이메일 인증 완료 여부 확인
    for (let i = 0; i < managers.length; i++) {
      const m = managers[i];
      if (m.email !== m.originalEmail && !m.isVerified) {
        alert(`담당자 ${i + 1}의 변경된 이메일 인증을 완료해 주세요.`);
        return;
      }
    }

    fetch(`${baseUrl}/api/brand-info/update`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        brandId,
        currentBrandPw,
        newBrandPw,
        managers
      })
    })
      .then(res => res.json())
      .then(data => {
        alert(data.message);
        if (data.success) {
          setCurrentBrandPw('');
          setNewBrandPw('');
          const updated = managers.map(m => ({
            ...m,
            originalName: m.name,
            originalEmail: m.email,
            managerPw: '',
            isEditing: false,
            isVerified: true,
            isEmailSent: false,
            authCode: ''
          }));
          setManagers(updated);
        }
      })
      .catch(err => alert("수정 중 오류가 발생했습니다."));
  };

  const handleConfirmWithdraw = (e) => {
    e.preventDefault();
    if (!agreeWithdrawTerms) {
      alert("약관 동의 체크박스에 동의하셔야 탈퇴가 진행됩니다.");
      return;
    }
    if (!withdrawPw) {
      alert("탈퇴를 진행하려면 브랜드 비밀번호를 입력해 주세요.");
      return;
    }

    setIsWithdrawing(true);

    fetch(`${baseUrl}/api/brand-info/withdraw`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        brandId,
        currentBrandPw: withdrawPw
      })
    })
      .then(res => res.json())
      .then(data => {
        setIsWithdrawing(false);
        if (data.success) {
          alert(data.message);
          setShowWithdrawModal(false);
          if (onNavigate) onNavigate('main_logout');
        } else {
          alert(data.message);
        }
      })
      .catch(err => {
        setIsWithdrawing(false);
        alert("탈퇴 처리 중 오류가 발생했습니다.");
      });
  };

  if (isLoading) {
    return <div style={{ textAlign: 'center', padding: '100px' }}>회원 정보를 불러오는 중입니다...</div>;
  }

  return (
    <div style={styles.container}>
      <h2 style={styles.title}>회원 정보 관리</h2>

      <form onSubmit={handleUpdateInfo} style={{ width: '100%' }}>
        {/* 카드 1: 브랜드 기본 정보 */}
        <div style={styles.sectionCard}>
          <h3 style={styles.sectionTitle}>🏢 브랜드 기본 정보</h3>
          
          <div style={styles.formGroup}>
            <label style={styles.label}>브랜드 고유 번호 (brand_id)</label>
            <input type="text" value={brandId || ''} disabled style={{ ...styles.input, backgroundColor: '#f1f5f9' }} />
            <span style={styles.helperText}>브랜드 고유 번호는 변경할 수 없습니다.</span>
          </div>

          <div style={styles.formGroup}>
            <label style={styles.label}>기존 브랜드 비밀번호 <span style={{ color: '#ef4444' }}>*</span></label>
            <div style={styles.passwordWrapper}>
              <input
                type={showCurrentPw ? "text" : "password"}
                placeholder="정보 수정을 위해 기존 비밀번호를 입력해 주세요"
                value={currentBrandPw}
                onChange={(e) => setCurrentBrandPw(e.target.value)}
                style={{ ...styles.input, flex: 1 }}
              />
              <button type="button" onClick={() => setShowCurrentPw(!showCurrentPw)} style={styles.toggleBtn}>
                {showCurrentPw ? "숨김" : "보기"}
              </button>
            </div>
          </div>

          <div style={styles.formGroup}>
            <label style={styles.label}>새 브랜드 비밀번호 (선택)</label>
            <div style={styles.passwordWrapper}>
              <input
                type={showNewPw ? "text" : "password"}
                placeholder="변경할 경우에만 입력해 주세요"
                value={newBrandPw}
                onChange={(e) => setNewBrandPw(e.target.value)}
                style={{ ...styles.input, flex: 1 }}
              />
              <button type="button" onClick={() => setShowNewPw(!showNewPw)} style={styles.toggleBtn}>
                {showNewPw ? "숨김" : "보기"}
              </button>
            </div>
            <span style={styles.helperText}>영문, 숫자, 특수문자 포함 8자 이상</span>
          </div>
        </div>

        {/* 카드 2: 담당자 정보 */}
        <div style={styles.sectionCard}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '2px solid #f1f5f9', paddingBottom: '10px' }}>
            <h3 style={{ ...styles.sectionTitle, borderBottom: 'none', paddingBottom: 0, marginBottom: 0 }}>👤 담당자 정보</h3>
            {managers.length < 2 && (
              <button type="button" onClick={handleAddManager} style={styles.smallOutlineButton}>
                + 담당자 추가하기
              </button>
            )}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
            {managers.map((manager, idx) => (
              <div key={idx} style={styles.managerCard}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                  <div style={styles.managerTitle}>담당자 {idx + 1}</div>
                  <button
                    type="button"
                    onClick={() => toggleEditManager(idx)}
                    style={{
                      ...styles.smallOutlineButton,
                      backgroundColor: manager.isEditing ? '#f8fafc' : '#fff',
                      color: manager.isEditing ? '#ef4444' : '#0f172a',
                      borderColor: manager.isEditing ? '#fca5a5' : '#cbd5e1'
                    }}
                  >
                    {manager.isEditing ? '수정 취소' : '정보 수정'}
                  </button>
                </div>

                {/* 담당자 이름 */}
                <div style={styles.formGroup}>
                  <label style={styles.label}>담당자 이름</label>
                  <input
                    type="text"
                    value={manager.name || ''}
                    readOnly={!manager.isEditing}
                    onChange={(e) => handleManagerChange(idx, 'name', e.target.value)}
                    style={{
                      ...styles.input,
                      backgroundColor: manager.isEditing ? '#fff' : '#f8fafc',
                      color: manager.isEditing ? '#0f172a' : '#64748b'
                    }}
                    required
                  />
                </div>

                {/* 담당자 이메일 & 인증 영역 */}
                <div style={styles.formGroup}>
                  <label style={styles.label}>담당자 이메일</label>
                  <div style={styles.passwordWrapper}>
                    <input
                      type="email"
                      value={manager.email || ''}
                      readOnly={!manager.isEditing || (manager.isVerified && manager.email !== manager.originalEmail)}
                      onChange={(e) => handleManagerChange(idx, 'email', e.target.value)}
                      style={{
                        ...styles.input,
                        flex: 1,
                        backgroundColor: (manager.isEditing && !(manager.isVerified && manager.email !== manager.originalEmail)) ? '#fff' : '#f8fafc',
                        color: (manager.isEditing && !(manager.isVerified && manager.email !== manager.originalEmail)) ? '#0f172a' : '#64748b'
                      }}
                      required
                    />
                    {manager.isEditing && manager.email !== manager.originalEmail && (
                      <button
                        type="button"
                        onClick={() => sendAuthCode(idx)}
                        disabled={manager.isVerified}
                        style={{
                          ...styles.actionBtn,
                          backgroundColor: manager.isVerified ? '#94a3b8' : '#0f172a',
                          cursor: manager.isVerified ? 'default' : 'pointer'
                        }}
                      >
                        {manager.isVerified ? '인증 완료' : '인증번호 발송'}
                      </button>
                    )}
                  </div>
                </div>

                {/* 인증번호 입력 박스 */}
                {manager.isEditing && manager.isEmailSent && !manager.isVerified && (
                  <div style={styles.formGroup}>
                    <label style={styles.label}>인증번호 입력</label>
                    <div style={styles.passwordWrapper}>
                      <input
                        type="text"
                        placeholder="메일로 받은 6자리 숫자"
                        value={manager.authCode || ''}
                        onChange={(e) => handleManagerChange(idx, 'authCode', e.target.value)}
                        style={{ ...styles.input, flex: 1 }}
                      />
                      <button
                        type="button"
                        onClick={() => verifyAuthCode(idx)}
                        style={styles.actionBtn}
                      >
                        확인
                      </button>
                    </div>
                  </div>
                )}

                {/* 인증 성공 표시 */}
                {manager.isEditing && manager.email !== manager.originalEmail && manager.isVerified && (
                  <div style={{ color: '#16a34a', fontSize: '0.85rem', fontWeight: 'bold', marginTop: '-4px' }}>
                    ✓ 이메일 인증 완료
                  </div>
                )}

                {/* 새 담당자 비밀번호 */}
                <div style={styles.formGroup}>
                  <label style={styles.label}>새 담당자 비밀번호 (선택)</label>
                  <input
                    type="password"
                    placeholder={manager.isEditing ? "변경할 경우에만 입력해 주세요" : "수정하기 버튼을 클릭하면 입력 가능합니다"}
                    readOnly={!manager.isEditing}
                    value={manager.managerPw || ''}
                    onChange={(e) => handleManagerChange(idx, 'managerPw', e.target.value)}
                    style={{
                      ...styles.input,
                      backgroundColor: manager.isEditing ? '#fff' : '#f8fafc',
                      color: manager.isEditing ? '#0f172a' : '#64748b'
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 하단 저장 및 탈퇴 영역 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '10px' }}>
          <button type="button" onClick={() => { setShowWithdrawModal(true); setAgreeWithdrawTerms(false); setWithdrawPw(''); }} style={styles.withdrawLinkBtn}>
            회원 탈퇴하기
          </button>
          <button type="submit" style={styles.primaryButton}>
            수정사항 저장하기
          </button>
        </div>
      </form>

      {/* 회원 탈퇴 모달 */}
      {showWithdrawModal && (
        <div style={styles.modalOverlay}>
          <div style={styles.modalContent}>
            <h3 style={styles.modalTitle}>⚠️ 회원 탈퇴 안내 및 약관 동의</h3>
            <p style={{ fontSize: '0.88rem', color: '#64748b', marginBottom: '15px' }}>
              탈퇴를 진행하시기 전 아래 약관 및 개인정보 처리방침을 반드시 확인해 주세요.
            </p>

            <div style={styles.termsBox}>
              <h4 style={styles.termsSubTitle}>1. 개인정보 처리 및 데이터 보관 정책</h4>
              <ul style={styles.termsList}>
                <li>탈퇴 신청 즉시 브랜드 계정은 <strong>탈퇴 유예 상태(WITHDRAWING)</strong>로 전환됩니다.[cite: 30]</li>
                <li><strong>30일의 유예 기간</strong> 동안 언제든지 다시 로그인하여 탈퇴를 취소할 수 있습니다.[cite: 30]</li>
                <li>30일 경과 시 모든 계정 정보 및 브랜드 데이터가 영구 파기됩니다.[cite: 30]</li>
              </ul>

              <h4 style={styles.termsSubTitle}>2. 구독 서비스 및 환불 정책</h4>
              <ul style={styles.termsList}>
                <li>이용 중이던 정기 결제 플랜은 즉시 해지 예약 처리됩니다.</li>
                <li>이미 결제된 당월 유료 구독 이용권의 잔여 기간은 중도 환불이 불가합니다.</li>
              </ul>
            </div>

            <form onSubmit={handleConfirmWithdraw} style={{ marginTop: '15px' }}>
              <div style={styles.agreeBox}>
                <label style={styles.agreeLabel}>
                  <input
                    type="checkbox"
                    checked={agreeWithdrawTerms}
                    onChange={(e) => setAgreeWithdrawTerms(e.target.checked)}
                    style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                  />
                  <span>
                    <strong style={{ color: '#dc2626' }}>[필수]</strong> 위 개인정보 처리, 탈퇴 유예, 구독 및 환불 관련 약관을 모두 확인하였으며 회원 탈퇴에 동의합니다.
                  </span>
                </label>
              </div>

              <div style={{ marginTop: '15px' }}>
                <label style={styles.label}>본인 확인 (브랜드 비밀번호 입력)</label>
                <input
                  type="password"
                  placeholder="기존 브랜드 비밀번호를 입력하세요"
                  value={withdrawPw}
                  onChange={(e) => setWithdrawPw(e.target.value)}
                  style={styles.input}
                  required
                />
              </div>

              <div style={styles.modalButtons}>
                <button type="button" onClick={() => setShowWithdrawModal(false)} style={styles.closeBtn}>
                  취소 (돌아가기)
                </button>
                <button
                  type="submit"
                  disabled={!agreeWithdrawTerms || isWithdrawing}
                  style={{
                    ...styles.primaryButton,
                    backgroundColor: agreeWithdrawTerms ? '#dc2626' : '#fca5a5',
                    cursor: agreeWithdrawTerms ? 'pointer' : 'not-allowed'
                  }}
                >
                  {isWithdrawing ? '처리 중...' : '동의 및 탈퇴 신청'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

const styles = {
  container: { 
    maxWidth: '720px', 
    width: '100%', 
    margin: '0 auto', 
    fontFamily: 'sans-serif', 
    boxSizing: 'border-box' 
  },
  title: { textAlign: 'center', marginBottom: '35px', color: '#0f172a', fontSize: '1.8rem', fontWeight: 'bold' },
  sectionCard: { backgroundColor: '#fff', borderRadius: '12px', padding: '25px', marginBottom: '25px', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' },
  sectionTitle: { fontSize: '1.2rem', fontWeight: 'bold', color: '#1e293b', marginBottom: '20px', borderBottom: '2px solid #f1f5f9', paddingBottom: '10px' },
  formGroup: { display: 'flex', flexDirection: 'column', gap: '8px', textAlign: 'left', marginBottom: '16px' },
  label: { fontSize: '0.88rem', fontWeight: 'bold', color: '#333' },
  input: { padding: '12px 14px', fontSize: '0.95rem', border: '1px solid #cbd5e1', borderRadius: '6px', outline: 'none', backgroundColor: '#fff', width: '100%', boxSizing: 'border-box' },
  passwordWrapper: { display: 'flex', gap: '8px', alignItems: 'center' },
  toggleBtn: { padding: '12px 14px', backgroundColor: '#f8fafc', border: '1px solid #cbd5e1', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: '600', color: '#475569', whiteSpace: 'nowrap' },
  actionBtn: { padding: '12px 16px', backgroundColor: '#0f172a', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 'bold', whiteSpace: 'nowrap' },
  helperText: { fontSize: '0.8rem', color: '#64748b' },
  smallOutlineButton: { padding: '6px 12px', backgroundColor: '#fff', border: '1px solid #cbd5e1', color: '#475569', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 'bold' },
  managerCard: { display: 'flex', flexDirection: 'column', gap: '12px', padding: '16px', backgroundColor: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' },
  managerTitle: { fontSize: '0.95rem', fontWeight: 'bold', color: '#0f172a' },
  primaryButton: { padding: '12px 24px', backgroundColor: '#0f172a', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold', fontSize: '0.95rem' },
  withdrawLinkBtn: { background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: '0.88rem', textDecoration: 'underline' },

  modalOverlay: { position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000 },
  modalContent: { width: '90%', maxWidth: '520px', backgroundColor: '#fff', padding: '28px', borderRadius: '12px', boxShadow: '0 4px 20px rgba(0,0,0,0.15)', textAlign: 'left' },
  modalTitle: { fontSize: '1.25rem', fontWeight: 'bold', color: '#111', marginBottom: '8px' },
  termsBox: { maxHeight: '200px', overflowY: 'auto', backgroundColor: '#f8fafc', padding: '16px', borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '0.85rem', color: '#334155' },
  termsSubTitle: { fontSize: '0.9rem', fontWeight: 'bold', color: '#0f172a', marginTop: '10px', marginBottom: '6px' },
  termsList: { paddingLeft: '18px', margin: '0 0 10px 0', lineHeight: '1.5' },
  agreeBox: { padding: '12px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', marginTop: '15px' },
  agreeLabel: { display: 'flex', alignItems: 'flex-start', gap: '10px', fontSize: '0.85rem', color: '#1e293b', cursor: 'pointer', lineHeight: '1.4' },
  modalButtons: { display: 'flex', gap: '10px', marginTop: '20px', justifyContent: 'flex-end' },
  closeBtn: { padding: '10px 20px', backgroundColor: '#e2e8f0', color: '#334155', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' }
};

export default BrandInfoPage;