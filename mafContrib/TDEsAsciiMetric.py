# TDEs metric with input ascii lightcurve.
# lixl@udel.edu

import os
import numpy as np
from lsst.sims.maf.metrics import BaseMetric
import lsst.sims.maf.utils as utils
from lsst.utils import getPackageDir

__all__ = ['TDEsAsciiMetric']

class TDEsAsciiMetric(BaseMetric):
    """Based on the transientMetric, but uses an ascii input file and provides option to write out lightcurve.
    
    Calculate what fraction of the TDEs would be detected. Best paired with a spatial slicer.
    The lightcurve in input is an ascii file per photometric band so that different lightcurve
    shapes can be implemented.

    This metric is designed to evaluate the detection of TDEs with the requirement that allows discrimination 
    from supernova. The structure is similar to TransientAsciiMetric, but the condition parameters are different.
    It can be used to put requirements on the number of observations or filters before peak, near peak and post peak. 

    Parameters
    ----------
    asciifile : str (None)
        The ascii file containing the inputs for the lightcurve (per filter):
        File should contain three columns - ['ph', 'mag', 'flt'] -
        of phase/epoch (in days), magnitude (in a particular filter), and filter.
        If none, will load default from /data dir in repo
    
    detectSNR : dict, optional
        An observation will be counted toward the discovery criteria if the light curve SNR
        is higher than detectSNR (specified per bandpass).
        Values must be provided for each filter which should be considered in the lightcurve.
        Default is {'u': 5, 'g': 5, 'r': 5, 'i': 5, 'z': 5, 'y': 5}
    
    Light curve parameters
    -------------
    epochStart: float
        The start epoch in ascii file.
        
    peakEpoch: float
        The epoch of the peak in ascii file.

    nearPeakT: float
        The days near peak. Epoches from (peakEpoch - nearPeakT/2) to (peakEpoch + nearPeakT/2) 
        are considered as near peak.
    
    postPeakT: float
        The days within postPeakT are considered as post peak. 
        Post peak epoch is from (peakEpoch + nearPeakT/2) to (peakEpoch + nearPeakT/2 + postPeakT).

    nPhaseCheck: float
        Number of phases to check.
        Default 1.
    
    Condition parameters
    --------------
    nObsTotal: dict
        Minimum required total number of observations in each band.
        Default None (becomes) {'u': 0, 'g': 0, 'r': 0, 'i': 0, 'z': 0, 'y': 0}

    nObsPrePeak: float
        Number of observations before peak.
        Default 0

    nObsNearPeak: dict
        Minimum required number of observations in each band near peak.
        Default None (becomes) {'u': 0, 'g': 0, 'r': 0, 'i': 0, 'z': 0, 'y': 0},
    
    nFiltersNearPeak: float
        Number of filters near peak.
        Default 0

    nObsPostPeak: float
        Number of observations after peak.
        Default 0

    nFiltersPostPeak: float
        Number of filters after peak. 
        Default 0

    Output control parameters
    --------------
    dataout : bool, optional
        If True, metric returns full lightcurve at each point. Note that this will potentially
        create a very large metric output data file. 
        If False, metric returns the number of transients detected.

    """

    def __init__(self, asciifile=None, metricName = 'TDEsAsciiMetric', 
    			 mjdCol = 'observationStartMJD', m5Col = 'fiveSigmaDepth', filterCol = 'filter', 
                 detectSNR = None,
                 epochStart = -20, peakEpoch = 0, nearPeakT=5, postPeakT=10, nPhaseCheck = 1, 
                 nObsTotal = None,
                 nObsPrePeak = 0,
                 nObsNearPeak = None,
                 nFiltersNearPeak = 0, 
                 nObsPostPeak = 0, nFiltersPostPeak = 0, 
                 dataout=False, **kwargs):

        if asciifile is None:
            asciifile = os.path.join(getPackageDir('sims_maf_contrib'), 'data/tde/TDEfaintfast_z0.1.dat')
        if detectSNR is None:
            detectSNR = {'u': 5, 'g': 5, 'r': 5, 'i': 5, 'z': 5, 'y': 5}
        if nObsTotal is None:
            nObsTotal = {'u': 0, 'g': 0, 'r': 0, 'i': 0, 'z': 0, 'y': 0}
        if nObsNearPeak is None:
            nObsNearPeak = {'u': 0, 'g': 0, 'r': 0, 'i': 0, 'z': 0, 'y': 0}

        self.mjdCol = mjdCol
        self.m5Col = m5Col
        self.filterCol = filterCol
        self.detectSNR = detectSNR
        self.dataout = dataout

        # light curve parameters
        self.epochStart = epochStart
        self.peakEpoch = peakEpoch
        self.nearPeakT = nearPeakT
        self.postPeakT = postPeakT
        self.nPhaseCheck = nPhaseCheck

        # condition parameters
        self.nObsTotal = nObsTotal
        self.nObsPrePeak = nObsPrePeak
        self.nObsNearPeak = nObsNearPeak
        self.nFiltersNearPeak = nFiltersNearPeak
        self.nObsPostPeak = nObsPostPeak
        self.nFiltersPostPeak = nFiltersPostPeak

        # if you want to get the light curve in output you need to define the metricDtype as object
        if self.dataout:
            super(TDEsAsciiMetric, self).__init__(col=[self.mjdCol, self.m5Col, self.filterCol],
                                                       metricDtype='object', units='', 
                                                       metricName='TDEsAsciiMetric', **kwargs)
        else:
            super(TDEsAsciiMetric, self).__init__(col=[self.mjdCol, self.m5Col, self.filterCol],
                                                       units='Fraction Detected', 
                                                       metricName='TDEsAsciiMetric', **kwargs)

        # Read the light curve template from disk.
        self._read_lightCurve(asciifile)

        # Calculate some properties of the lightcurve that don't vary from slicepoint to slicepoint
        self.transDuration = self.lcv_template['ph'].max() - self.lcv_template['ph'].min()  # days
        # tshifts tracks the timeoffsets for each 'shifted' lightcurve
        self.tshifts = np.arange(self.nPhaseCheck) * self.transDuration / float(self.nPhaseCheck)
        # Separate the lightcurve into filters, so we don't have to do that each time.
        self.lc = {}
        lc_filters = set(self.lcv_template['flt'])
        for f in lc_filters:
            self.lc[f] = self.lcv_template[self.lcv_template['flt'] == f]

    def _read_lightCurve(self, asciifile):
        # read lightcurve template from an ascii file.
        if not os.path.isfile(asciifile):
            raise IOError('Could not find lightcurve ascii file %s' % (asciifile))
        # Lightcurve template should consist of rows of time (in days), mag, and filter.
        self.lcv_template = np.genfromtxt(asciifile, dtype=[('ph', 'f8'), ('mag', 'f8'), ('flt', 'U1')])

    def sample_lightCurve(self, time, filters):
        # sample light curve template at time and in filters of observations (time and filters)
        lcMags = np.zeros(time.size, dtype=float)
        for f in set(filters):
            matches = np.where(filters == f)
            # Generate magnitudes at the appropriate times
            lcMags[matches] = np.interp(time[matches], self.lc[f]['ph'], self.lc[f]['mag'])
        return lcMags

    def snr2std(self, snr):
        # standard deviation of magnitudes.
        std = 2.5 * np.log10(1 + 1/snr)
        return std 

    def run(self, dataSlice, slicePoint=None):
        """"Calculate the detectability of a transient with the specified lightcurve.

        If self.dataout is True, then returns the full lightcurve for each object instead of the total
        number of transients that are detected.

        Parameters
        ----------
        dataSlice : numpy.array
            Numpy structured array containing the data related to the visits provided by the slicer.
        slicePoint : dict, optional
            Dictionary containing information about the slicepoint currently active in the slicer.

        Returns
        -------
        float or a list of dicts
            The total number of transients that could be detected. (if dataout is False)
            Each dictionary with arrays of 'tshift', 'expMJD', 'm5', 'filters', 'lcNumber', 'lcEpoch', 
            'prePeakCheck' 'nearPeakCheck', 'postPeakCheck', 'lcMags', 'lcSNR',
            'lcMagsStd', 'lcAboveThresh', 'detected'
        """
        # Sort the entire dataSlice in order of time.
        dataSlice.sort(order=self.mjdCol)
        tSpan = (dataSlice[self.mjdCol].max() - dataSlice[self.mjdCol].min()) # in days

        # Lightcurve number indicates how many repetitions this dataSlice will contain
        lcNumber = np.floor((dataSlice[self.mjdCol] - dataSlice[self.mjdCol].min()) / self.transDuration)
        ulcNumber = np.unique(lcNumber)

        nTransMax = 0
        nDetected = 0
        dataout_dict_list = []
        for tshift in self.tshifts:
            # lcEpoch are the translated time (in days) for the times of each observation
            lcEpoch = np.fmod(dataSlice[self.mjdCol] - dataSlice[self.mjdCol].min() + tshift,
                              self.transDuration) + self.epochStart
     
            # total number of transients possibly detected
            nTransMax += np.ceil(tSpan/self.transDuration)

            # generate the actual light curve
            lcFilters = dataSlice[self.filterCol]
            lcMags = self.sample_lightCurve(lcEpoch, lcFilters)
            lcSNR = utils.m52snr(lcMags, dataSlice[self.m5Col])

            # Identify detections above SNR for each filter
            lcAboveThresh = np.zeros(len(lcSNR), dtype=bool)
            for f in np.unique(lcFilters):
                filtermatch = np.where(dataSlice[self.filterCol] == f)
                lcAboveThresh[filtermatch] = np.where(lcSNR[filtermatch] >= self.detectSNR[f], True, False)
                
            # check conditions for each light curve
            lcDetect = np.ones(len(ulcNumber), dtype=bool)
            lcDetectOut = np.ones(len(lcNumber), dtype=bool)
            for i, lcN in enumerate(ulcNumber):

                lcN_idx = np.where(lcNumber == lcN)
                lcEpoch_i = lcEpoch[lcN_idx]
                lcFilters_i = lcFilters[lcN_idx]
                lcAboveThresh_i = lcAboveThresh[lcN_idx]
                
                #check total number of observations for each band
                for f in np.unique(lcFilters_i):
                    f_Idx = np.where(lcFilters_i==f)
                    if len( np.where(lcAboveThresh_i[f_Idx])[0] ) < self.nObsTotal[f]:
                        lcDetect[i] = False
                        lcDetectOut[lcN_idx] = False
                
                # number of observations before peak
                prePeakCheck = (lcEpoch_i < self.peakEpoch - self.nearPeakT/2)
                prePeakIdx = np.where(prePeakCheck == True)
                if len( np.where(lcAboveThresh_i[prePeakIdx])[0] ) < self.nObsPrePeak:
                    lcDetect[i] = False
                    lcDetectOut[lcN_idx] = False

                # check number of observations near peak for each band
                nearPeakCheck = (lcEpoch_i >= self.peakEpoch - self.nearPeakT/2) & \
                                (lcEpoch_i <= self.peakEpoch + self.nearPeakT/2)
                nearPeakIdx = np.where(nearPeakCheck==True)
                
                for f in np.unique(lcFilters_i):
                    nearPeakIdx_f = np.intersect1d( nearPeakIdx, np.where(lcFilters_i==f) )
                    if len( np.where(lcAboveThresh_i[nearPeakIdx_f])[0] ) < self.nObsNearPeak[f]:
                        lcDetect[i] = False
                        lcDetectOut[lcN_idx] = False

                # check number of filters near peak
                filtersNearPeakIdx = np.intersect1d(nearPeakIdx, np.where(lcAboveThresh_i)[0])
                if len( np.unique(lcFilters_i[filtersNearPeakIdx]) ) < self.nFiltersNearPeak:
                        lcDetect[i] = False
                        lcDetectOut[lcN_idx] = False

                ## check number of observations post peak
                # postPeakCheck 
                postPeakCheck = (lcEpoch_i >= self.peakEpoch + self.nearPeakT/2) & \
                                (lcEpoch_i <= self.peakEpoch + self.nearPeakT/2 + self.postPeakT )
                postPeakIdx = np.where(postPeakCheck == True)
                if len( np.where(lcAboveThresh_i[postPeakIdx])[0] ) < self.nObsPostPeak:
                    lcDetect[i] = False
                    lcDetectOut[lcN_idx] = False

                # check number of filters post peak
                filtersPostPeakIdx = np.intersect1d(postPeakIdx, np.where(lcAboveThresh_i)[0])
                if len( np.unique(lcFilters_i[filtersPostPeakIdx]) ) < self.nFiltersPostPeak:
                        lcDetect[i] = False
                        lcDetectOut[lcN_idx] = False

            # return values   
            nDetected += len(np.where(lcDetect == True)[0])
            prePeakCheck = (lcEpoch <= self.peakEpoch - self.nearPeakT/2) 
            nearPeakCheck = (lcEpoch >= (self.peakEpoch - self.nearPeakT/2)) & \
                            (lcEpoch <= (self.peakEpoch + self.nearPeakT/2) )
            postPeakCheck = (lcEpoch >= (self.peakEpoch + self.nearPeakT/2)) & \
                            (lcEpoch <= (self.peakEpoch + self.nearPeakT/2 + self.postPeakT) )

            # create a dict for each tshift
            if self.dataout:
                dataout_dict_tshift = {'tshift': np.repeat(tshift, len(lcEpoch)),
                                       'timeMJD': dataSlice[self.mjdCol],
                                       'm5': dataSlice[self.m5Col],
                                       'filters': dataSlice[self.filterCol],
                                       'lcNumber': lcNumber,
                                       'lcEpoch': lcEpoch,
                                       'prePeakCheck': prePeakCheck,
                                       'nearPeakCheck': nearPeakCheck,
                                       'postPeakCheck': postPeakCheck,
                                       'lcMags': lcMags,
                                       'lcSNR': lcSNR,
                                       'lcMagsStd': self.snr2std(lcSNR),
                                       'lcAboveThresh': lcAboveThresh,
                                       'detected': lcDetectOut}

                dataout_dict_list.append(dataout_dict_tshift)

        if self.dataout:
            # the output is a list of dicts which contain parameters for each phase 
            return dataout_dict_list

        else: 
            # return the fraction detected
            return float(nDetected / nTransMax) if nTransMax!=0 else 0.


