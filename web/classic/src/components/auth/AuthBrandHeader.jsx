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

const AuthBrandHeader = () => {
  return (
    <div className='auth-brand-header'>
      <div className='auth-brand-logo-wrap'>
        <img src='/logo_1tok.jpg' alt='1tok' className='auth-brand-logo' />
      </div>
      <div className='auth-brand-copy'>
        <div className='auth-brand-title'>小红花技术领袖俱乐部</div>
        <div className='auth-brand-desc'>旗下 AI 服务平台</div>
      </div>
    </div>
  );
};

export default AuthBrandHeader;