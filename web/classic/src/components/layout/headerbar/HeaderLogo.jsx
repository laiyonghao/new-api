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
import { Link } from 'react-router-dom';
import SkeletonWrapper from '../components/SkeletonWrapper';

const HeaderLogo = ({
  isMobile,
  isConsoleRoute,
  isLoading,
}) => {
  if (isMobile && isConsoleRoute) {
    return null;
  }

  return (
    <Link
      to='/'
      className='landing-nav-brand'
      aria-label='1tok，小红花技术领袖俱乐部旗下 AI 服务平台'
    >
      <span className='landing-nav-logo-wrap'>
        <span className='landing-nav-logo landing-nav-logo-main'>
          <SkeletonWrapper loading={isLoading} type='image' />
          <img
            src='/logo_1tok.jpg'
            alt='1tok'
            className={!isLoading ? 'opacity-100' : 'opacity-0'}
          />
        </span>
      </span>
      <span className='landing-nav-brand-copy'>
        <span className='landing-nav-brand-title'>小红花技术领袖俱乐部</span>
        <span className='landing-nav-brand-desc'>旗下 AI 服务平台</span>
      </span>
    </Link>
  );
};

export default HeaderLogo;
