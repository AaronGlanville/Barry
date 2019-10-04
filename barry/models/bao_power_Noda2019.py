import logging
from functools import lru_cache

import numpy as np
from scipy.interpolate import splev, splrep
from scipy import integrate
from barry.models.bao_power import PowerSpectrumFit
from barry.cosmology.camb_generator import Omega_m_z


class PowerNoda2019(PowerSpectrumFit):
    """ P(k) model inspired from Noda 2019.

    See https://ui.adsabs.harvard.edu/abs/2019arXiv190106854N for details.

    """

    def __init__(self, name="Pk Noda 2019", fix_params=None, gammaval=None, smooth_type="hinton2017", recon=False, postprocess=None, smooth=False, correction=None):
        self.recon = recon
        self.recon_smoothing_scale = None
        super().__init__(name=name, fix_params=fix_params, smooth_type=smooth_type, postprocess=postprocess, smooth=smooth, correction=correction)

        self.fit_omega_m = fix_params is None or "om" not in fix_params
        self.fit_growth = fix_params is None or "f" not in fix_params
        self.fit_gamma = self.recon and (fix_params is None or "gamma" not in fix_params)
        self.nmu = 100
        self.mu = np.linspace(0.0, 1.0, self.nmu)
        self.smoothing_kernel = None

        if gammaval is None:
            if self.recon:
                gammaval = 4.0
            else:
                gammaval = 1.0
        self.gammaval = gammaval
        self.set_default("gamma", self.gammaval)

    @lru_cache(maxsize=32)
    def get_growth(self, om):
        return Omega_m_z(om, self.camb.redshift) ** 0.55

    @lru_cache(maxsize=32)
    def get_pt_data(self, om):
        return self.PT.get_data(om=om)

    @lru_cache(maxsize=8192)
    def get_damping(self, growth, om):
        return -np.outer((1.0 + (2.0 + growth) * growth * self.mu ** 2) * self.get_pt_data(om)["sigma_dd_rs"] + (growth * self.mu ** 2 * (self.mu ** 2 - 1.0)) * self.get_pt_data(om)["sigma_ss_rs"], ks ** 2)

    @lru_cache(maxsize=8192)
    def apply_gamma(self, damping, gamma):
        return np.exp(damping/gamma)

    def set_data(self, data):
        super().set_data(data)
        # Compute the smoothing kernel (assumes a Gaussian smoothing kernel)
        if self.recon:
            self.smoothing_kernel = np.exp(-self.camb.ks ** 2 * self.recon_smoothing_scale ** 2 / 2.0)

    def declare_parameters(self):
        super().declare_parameters()
        self.add_param("f", r"$f$", 0.01, 1.0, 0.5)  # Growth rate of structure
        self.add_param("gamma", r"$\gamma_{rec}$", 1.0, 8.0, self.gammaval)  # Describes the sharpening of the BAO post-reconstruction
        self.add_param("A", r"$A$", -10, 30.0, 10)  # Fingers-of-god damping

    def compute_power_spectrum(self, k, p, smooth=False):
        """ Computes the power spectrum model at k/alpha using the Ding et. al., 2018 EFT0 model
        
        Parameters
        ----------
        k : np.ndarray
            Array of wavenumbers to compute
        p : dict
            dictionary of parameter names to their values
            
        Returns
        -------
        array
            pk_final - The power spectrum at the dilated k-values
        
        """

        # Get the basic power spectrum components
        ks = self.camb.ks
        pk_smooth_lin, pk_ratio = self.compute_basic_power_spectrum(p["om"])

        # Compute the growth rate depending on what we have left as free parameters
        if self.fit_growth:
            growth = p["f"]
        else:
            growth = self.get_growth(p["om"])

        # Set the value of gamma for the BAO damping
        if self.fit_gamma:
            gamma = p["gamma"]
        else:
            gamma = self.gammaval

        # Lets round some things for the sake of numerical speed
        om = np.round(p["om"], decimals=5)
        growth = np.round(growth, decimals=5)
        gamma = np.round(gamma, decimals=5)

        # Compute the BAO damping/propagator
        propagator = self.apply_gamma(self.get_damping(growth, om), gamma)

        # Compute the smooth model
        if self.recon:
            kaiser_prefac = 1.0 + np.outer(growth / p["b"] * self.mu ** 2, 1.0 - self.smoothing_kernel)
        else:
            kaiser_prefac = 1.0 + np.tile(growth / p["b"] * self.mu ** 2, (len(ks), 1)).T
        fog = np.exp(-p["A"] * ks ** 2)
        pk_smooth = p["b"] ** 2 * pk_smooth_lin * fog

        # Compute the non-linear SPT correction to the smooth power spectrum
        pk_spt = (self.get_pt_data(om)["Pdd_spt"] + 2.0 * np.outer(growth / p["b"] * self.mu ** 2, self.get_pt_data(om)["Pdt_spt"])
            + np.outer((growth / p["b"] * self.mu ** 2) ** 2, self.get_pt_data(om)["Ptt_spt"]))

        # Integrate over mu
        if smooth:
            pk1d = integrate.simps(pk_smooth * ((1.0 + 0.0 * pk_ratio * propagator) * kaiser_prefac ** 2 + pk_spt), self.mu, axis=0)
        else:
            pk1d = integrate.simps(pk_smooth * ((1.0 + pk_ratio * propagator) * kaiser_prefac ** 2 + pk_spt), self.mu, axis=0)

        pk_final = splev(k / p["alpha"], splrep(ks, pk1d))

        return pk_final


if __name__ == "__main__":

    import sys
    import timeit
    from barry.datasets.dataset_power_spectrum import PowerSpectrum_SDSS_DR12_Z061_NGC

    sys.path.append("../..")
    logging.basicConfig(level=logging.DEBUG, format="[%(levelname)7s |%(funcName)20s]   %(message)s")
    logging.getLogger("matplotlib").setLevel(logging.ERROR)

    dataset = PowerSpectrum_SDSS_DR12_Z061_NGC(recon=False)
    data = dataset.get_data()
    model_pre = PowerNoda2019(recon=False)
    model_pre.set_data(data)

    dataset = PowerSpectrum_SDSS_DR12_Z061_NGC(recon=True)
    data = dataset.get_data()
    model_post = PowerNoda2019(recon=True)
    model_post.set_data(data)

    p = {"om": 0.3, "alpha": 1.0, "A": 7.0, "b": 1.6, "gamma": 4.0}
    for v in np.linspace(1.0, 20, 20):
        p["A"] = v
        print(v, model_post.get_likelihood(p))

    n = 200

    def test_pre():
        model_pre.get_likelihood(p, data[0])

    def test_post():
        model_post.get_likelihood(p, data[0])

    print("Pre-reconstruction likelihood takes on average, %.2f milliseconds" % (timeit.timeit(test_pre, number=n) * 1000 / n))
    print("Post-reconstruction likelihood takes on average, %.2f milliseconds" % (timeit.timeit(test_post, number=n) * 1000 / n))

    if True:
        p, minv = model_pre.optimize()
        print("Pre reconstruction optimisation:")
        print(p)
        print(minv)
        model_pre.plot(p)

        print("Post reconstruction optimisation:")
        p, minv = model_post.optimize()
        print(p)
        print(minv)
        model_post.plot(p)