'''This file is part of AeoLiS.
   
AeoLiS is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
   
AeoLiS is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
   
You should have received a copy of the GNU General Public License
along with AeoLiS.  If not, see <http://www.gnu.org/licenses/>.
   
AeoLiS  Copyright (C) 2015 Bas Hoonhout

bas.hoonhout@deltares.nl         b.m.hoonhout@tudelft.nl
Deltares                         Delft University of Technology
Unit of Hydraulic Engineering    Faculty of Civil Engineering and Geosciences
Boussinesqweg 1                  Stevinweg 1
2629 HVDelft                     2628CN Delft
The Netherlands                  The Netherlands

'''


from __future__ import absolute_import, division

import logging
import numpy as np
import scipy
import matplotlib.pyplot as plt

# package modules
from aeolis.utils import *


# initialize logger
logger = logging.getLogger(__name__)


def compute(s, p):
    '''Compute wind velocity threshold based on bed surface properties

    Computes wind velocity threshold based on grain size fractions,
    bed slope, soil moisture content, air humidity, the presence of
    roughness elements and a non-erodible layer. All bed surface 
    properties increase the current wind velocity threshold, except
    for the grain size fractions. Therefore, the computation is 
    initialized by the grain size fractions and subsequently altered 
    by the other bed surface properties.

    Parameters
    ----------
    s : dict
        Spatial grids
    p : dict
        Model configuration parameters

    Returns
    -------
    dict
        Spatial grids

    See Also
    --------
    compute_grainsize
    compute_bedslope
    compute_moisture
    compute_humidity
    compute_sheltering
    non_erodible

    '''

    if p['process_threshold'] and p['threshold_file'] is None:

        if p['th_grainsize']:
            s = compute_grainsize(s, p)
        if p['th_bedslope']:
            s = compute_bedslope(s, p)
        if p['th_moisture']:
            s = compute_moisture(s, p)
        else:
            # no aeolian transport when the bed level is lower than the water level
            if p['process_tide']:
                ix = s['zb'] - s['zs'] < - p['eps']
                s['uth'][ix] = np.inf
                
        if p['th_drylayer']:
            s = dry_layer(s, p)
        if p['th_humidity']:
            s = compute_humidity(s, p)
        if p['th_salt']:
            s = compute_salt(s, p)
        if p['th_sheltering']:
            s = compute_sheltering(s, p)
                    
        # apply complex mask
        nf = p['nfractions']
        for i_nf in range(nf):
            s['uth'][:, :, i_nf] = apply_mask(s['uth'][:, :, i_nf], s['threshold_mask'])

        s['uthf'] = s['uth'].copy()
        
    #non-erodible layer (NEW)
    if p['th_nelayer']:
        s = non_erodible(s,p)

    return s


def compute_grainsize(s, p):
    '''Compute wind velocity threshold based on grain size fractions following Bagnold (1937)

    Parameters
    ----------
    s : dict
        Spatial grids
    p : dict
        Model configuration parameters

    Returns
    -------
    dict
        Spatial grids

    '''

    s['uth'][:,:,:] = 1.
    s['uth'][:,:,:] = p['Aa'] * np.sqrt((p['rhog'] - p['rhoa']) / p['rhoa'] * p['g'] * p['grain_size']) 
    
    # Shear velocity threshold based on grainsize only (aerodynamic entrainment)
    s['uth0'] = s['uth'].copy()
    
    return s


def compute_bedslope(s, p):
    '''Modify wind velocity threshold based on bed slopes following Dyer (1986)

    Parameters
    ----------
    s : dict
        Spatial grids
    p : dict
        Model configuration parameters

    Returns
    -------
    dict
        Spatial grids

    '''

    return s


def compute_moisture(s, p):
    '''Modify wind velocity threshold based on soil moisture content following
    Belly (1964) or Hotta (1984)

    Parameters
    ----------
    s : dict
        Spatial grids
    p : dict
        Model configuration parameters

    Returns
    -------
    dict
        Spatial grids

    '''

    nf = p['nfractions']
    
    # convert from volumetric content (percentage of volume) to
    # geotechnical mass content (percentage of dry mass)
    mg = (s['moist'][:,:] * p['rhow'] / (p['rhog'] * (1. - p['porosity'])))
    mg = mg[:,:,np.newaxis].repeat(nf, axis=2)
    ix = mg > p['resw_moist']* p['rhow'] / (p['rhog'] * (1. - p['porosity'])) + 0.005
    
    
    if p['method_moist_threshold'].lower() == 'belly_johnson':
        s['uth'][ix] *= np.maximum(1., 1.8+0.6*np.log10(mg[ix] * 100.))
    elif p['method_moist_threshold'].lower() == 'hotta':
        s['uth'][ix] += 7.5 * mg[ix]
    elif p['method_moist_threshold'].lower() == 'chepil':
        s['uth'][ix] = np.sqrt( s['uth'][ix] ** 2 + 0.6 * mg[ix] ** 2 / (p['rhoa'] * p['w1_5'] ** 2))
    elif p['method_moist_threshold'].lower() == 'saleh_fryear':
        s['uth'][ix] = 0.305 + 0.022 * mg[ix] / p['w1_5'] + 0.506 * (mg[ix] / p['w1_5']) ** 2
    elif p['method_moist_threshold'].lower() == 'saleh_fryear_mod':
        s['uth'][ix] += 0.022 * mg[ix] / p['w1_5'] + 0.506 * (mg[ix] / p['w1_5']) ** 2
    elif p['method_moist_threshold'].lower() == 'shao':
        s['uth'][ix] *= np.exp(22.7 * mg[ix])
    elif p['method_moist_threshold'].lower() == 'dong_2002':
        d = np.sum(p['grain_size'] * p['grain_dist']) * 1000
        if d < 0.135:
            K = 2.51
        elif d < 0.150:
            K = 2.05
        elif d < 0.200:
            K = 2.75
        elif d < 0.250:
            K = 1.59
        elif d < 0.400:
            K = 1.87
        else:
            K = 2.15
        s['uth'][ix] *= np.sqrt(1 + K * 100 * mg[ix])
    elif p['method_moist_threshold'].lower() == 'gregory_darwish':
        d = np.sum(p['grain_size'] * p['grain_dist'])
        wdiff = np.zeros(mg.shape)
        wdiff[ix] = np.maximum(mg[ix] - 0.5 * p['w1_5'],0)
        a1 = 6.12e-05
        a2 = 738.8
        a3 = 0.1
        s['uth'][ix] *= np.sqrt(1 + mg[ix] + 6 / np.pi * a1 / (p['rhog'] * p['g'] * d ** 2) \
                                + a2 / (p['rhow'] * p['g'] * d) * np.exp(-a3 * mg[ix] / p['w1_5']) * wdiff[ix])
    elif p['method_moist_threshold'].lower() == 'cornelis':
        d = np.sum(p['grain_size'] * p['grain_dist'])
        a1 = 0.013
        a2 = 1.7e-4
        a3 = 3e14
        s['uth'][ix] = np.sqrt(a1 * (1 + mg[ix] + a2 /((p['rhog'] - p['rhoa']) * p['g'] * d ** 2) \
                                      * (1 + a3 * 0.075 ** 2 * d / (10 ** 9 * np.exp(-6.5 * mg[ix] / p['w1_5']))) \
                                          * (p['rhog'] - p['rhoa']) / p['rhoa'] * p['g'] * d))
    elif p['method_moist_threshold'].lower() == 'dong_2007':
        d = np.sum(p['grain_size'] * p['grain_dist'])   
        s['uth'][ix] = 0.16 * np.sqrt((p['rhog'] - p['rhoa']) / p['rhoa'] * p['g'] * d) * (1 + 478.2 * mg[ix] ** 1.52)
    else:
        logger.log_and_raise('Unknown moisture formulation [%s]' % p['method_moist'], exc=ValueError)

    th_mg = (p['max_moist']/100 * p['rhow'] / (p['rhog'] * (1. - p['porosity'])))
    # should be .04 according to Pye and Tsoar
    # should be .064 according to Delgado-Fernandez (10% vol.)
    # .097 corresponds to 15%
    ix = mg > th_mg
    s['uth'][ix] = np.inf
    
    return s


#REMOVE?? CH
# def compute_humidity(s, p):
#     '''Modify wind velocity threshold based on air humidity following Arens (1996)

#     Parameters
#     ----------
#     s : dict
#         Spatial grids
#     p : dict
#         Model configuration parameters

#     Returns
#     -------
#     dict
#         Spatial grids

#     '''

#     nx = p['nx']+1
#     ny = p['ny']+1
#     nf = p['nfractions']

#     # compute effect of humidity on shear velocity threshold
#     H = 5.45 * (1. + .17 * (1. + np.cos(s['udir'])) - 2.11/100. + 2.11/(100. - s['meteo']['R']))
    
#     # modify shear velocity threshold
#     s['uth'] += H.reshape((ny,nx,1)).repeat(nf, axis=-1) # TODO: probably incorrect

#     return s


def compute_salt(s, p):
    '''Modify wind velocity threshold based on salt content following Nickling and Ecclestone (1981)

    Parameters
    ----------
    s : dict
        Spatial grids
    p : dict
        Model configuration parameters

    Returns
    -------
    dict
        Spatial grids

    '''

    nx = p['nx']+1
    ny = p['ny']+1
    nf = p['nfractions']

    # compute effect of salt content on shear velocity threshold
    cs = p['csalt'] * (1. - s['salt'][:,:,:1])
    CS = 1.03 * np.exp(.1027 * 1e3 * cs).repeat(nf, axis=-1)
    
    # modify shear velocity threshold
    s['uth'] *= CS

    return s


def compute_sheltering(s, p):
    '''Modify wind velocity threshold based on the presence of roughness elements following Raupach (1993)

    Raupach (1993) presents the following amplification factor for the
    shear velocity threshold due to the presence of roughness
    elements.

    .. math::
    
        R_t = \\frac{u_{*,th,s}}{u_{*,th,r}} 
            = \\sqrt{\\frac{\\tau_s''}{\\tau}} 
            = \\frac{1}{\\sqrt{\\left( 1 - m \\sigma \\lambda \\right)
                               \\left( 1 + m \\beta \\lambda \\right)}}

    :math:`m` is a constant smaller or equal to unity that accounts
    for the difference between the average stress on the bed surface
    :math:`\\tau_s` and the maximum stress on the bed surface
    :math:`\\tau_s''`.

    :math:`\\beta` is the stress partition coefficient defined as the
    ratio between the drag coefficient of the roughness element itself
    :math:`C_r` and the drag coefficient of the bare surface without
    roughness elements :math:`C_s`.

    :math:`\\sigma` is the shape coefficient defined as the basal area
    divided by the frontal area: :math:`\\frac{A_b}{A_f}`. For
    hemispheres :math:`\\sigma = 2`, for spheres :math:`\\sigma = 1`.

    :math:`\\lambda` is the roughness density defined as the number of
    elements per surface area :math:`\\frac{n}{S}` multiplied by the
    frontal area of a roughness element :math:`A_f`, also known as the
    frontal area index:

    .. math::

        \\lambda = \\frac{n b h}{S} = \\frac{n A_f}{S}

    If multiplied by :math:`\\sigma` the equation simplifies to the
    mass fraction of non-erodible elements:

    .. math::
    
        \\sigma \\lambda = \\frac{n A_b}{S} = \\sum_{k=n_0}^{n_k} \hat{w}^{\mathrm{bed}}_k

    where :math:`k` is the fraction index, :math:`n_0` is the smallest
    non-erodible fraction, :math:`n_k` is the largest non-erodible
    fraction and :math:`\hat{w}^{\mathrm{bed}}_k` is the mass fraction
    of sediment fraction :math:`k`. It is assumed that the fractions
    are ordered by increasing size.

    Substituting the derivation in the Raupach (1993) equation gives
    the formulation implemented in this function:

    .. math::
    
        u_{*,th,r} = u_{*,th,s} * \\sqrt{\\left( 1 - m \\sum_{k=n_0}^{n_k} \hat{w}^{\mathrm{bed}}_k \\right)
                                         \\left( 1 + m \\frac{\\beta}{\\sigma} \\sum_{k=n_0}^{n_k} \hat{w}^{\mathrm{bed}}_k \\right)}

    Parameters
    ----------
    s : dict
        Spatial grids
    p : dict
        Model configuration parameters

    Returns
    -------
    dict
        Spatial grids

    '''

    nx = p['nx']+1
    ny = p['ny']+1
    nf = p['nfractions']

    # mass fraction of non-erodible fractions used as roughness measure
    mass = s['mass'][:,:,0,:].reshape((-1,nf))
    gd = np.zeros((nx*ny,))
    for i in range(nf):
        ix = (s['ustar'] <= s['uth'][:,:,i]).flatten()
        gd[ix] += mass[ix,i]
    gd /= mass.sum(axis=-1)

    # compute inverse of shear stress ratio
    Rti = np.sqrt((1. - p['m'] * gd) * (1. + p['m'] * p['beta'] / p['sigma'] * gd))
    s['Rti'] = Rti

    # modify shear velocity threshold
    s['uth'] *= Rti.reshape((ny,nx,1)).repeat(nf, axis=-1)
    
    return s

def non_erodible(s,p): 
    '''Modify wind velocity threshold based on the presence of a 
    non-erodible layer.

    Parameters
    ----------
    s : dict
        Spatial grids
    p : dict
        Model configuration parameters

    Returns
    ------- 
    dict
        Spatial grids

    '''
    
    nf = p['nfractions']
    s['zne'][:,:] = p['ne_file'] 

    # Determine where ne-layer is "exposed"
    thuthlyr = 0.01
    ix = (s['zb'] <= s['zne'] + thuthlyr)
    
    # Smooth method
    # dzne = np.maximum( ( s['zne'] + thuthlyr - s['zb']) / thuthlyr, 0. )
    # for i in range(nf):
    #     duth = np.maximum( 2.* s['ustar'] - s['uth'][:,:,i], 0)
    #     s['uth'][ix,i] += duth[ix] * dzne[ix]
    
    # Hard method
    for i in range(nf):
        s['uth'][ix,i] = np.inf     
   
    
    return s    

