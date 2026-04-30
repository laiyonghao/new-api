/*
Copyright (C) 2025 QuantumNous

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

For commercial licensing, please contact support@quantumnous.com
*/

import React from 'react';
import { useLocation } from 'react-router-dom';

const FooterBar = () => {
  const location = useLocation();
  const isLandingRoute = location.pathname === '/';

  const currentYear = new Date().getFullYear();

  const landingGlobalFooter = (
    <footer className='landing-global-footer'>
      <div className='landing-global-footer-inner'>
        <div className='landing-global-footer-main'>
          <span>小红花技术领袖俱乐部 1tok © {currentYear}</span>
          {/* <span>企业采购、合同、发票与技术支持，以正式服务标准交付。</span> */}
        </div>
        {/* <div className='landing-global-footer-credit'>
          <span>技术底座</span>
          <a
            href='https://github.com/QuantumNous/new-api'
            target='_blank'
            rel='noopener noreferrer'
          >
            New API by QuantumNous
          </a>
        </div> */}
        <div className='landing-global-footer-credit'>
          <a
            href='//beian.miit.gov.cn/'
            target='_blank'
            title='粤ICP备2022094092号-1'
          >
            粤ICP备2022094092号-1
          </a>
        </div>
      </div>
    </footer>
  );

  if (isLandingRoute) {
    return (
      <>
        <footer className='landing-enterprise-footer'>
          <div className='landing-shell landing-enterprise-footer-inner'>
            <div className='landing-enterprise-footer-brand'>
              <img
                src='/logo_1tok.jpg'
                alt='1tok'
                className='landing-enterprise-footer-logo landing-enterprise-footer-logo-main'
              />
              <img
                src='/logo_xhh.png'
                alt='小红花技术领袖俱乐部'
                className='landing-enterprise-footer-logo'
              />
              <div>
                <div className='landing-enterprise-footer-name'>1tok</div>
                <div className='landing-enterprise-footer-desc'>
                  小红花技术领袖俱乐部旗下 AI 服务平台
                </div>
              </div>
            </div>
            <div className='landing-enterprise-footer-columns'>
              <div>
                <div className='landing-enterprise-footer-title'>企业服务</div>
                <p>合同采购 / 对公转账 / 合规发票 / 技术支持</p>
              </div>
              <div>
                <div className='landing-enterprise-footer-title'>安全承诺</div>
                <p>真实模型调用 / 传输加密 / 零日志策略 / 稳定转发</p>
              </div>
              <div>
                <div className='landing-enterprise-footer-title'>联系合作</div>
                <p>商务合作、企业咨询与大用量方案可通过站内入口联系团队</p>
              </div>
            </div>
          </div>
        </footer>

        {landingGlobalFooter}
      </>
    );
  }

  return landingGlobalFooter;
};

export default FooterBar;
