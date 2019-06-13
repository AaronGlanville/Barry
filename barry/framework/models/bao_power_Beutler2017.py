import logging
import numpy as np
from scipy.interpolate import splev, splrep
from barry.framework.models.bao_power import PowerSpectrumFit


class PowerBeutler2017(PowerSpectrumFit):

    def __init__(self, fix_params=["om"], smooth_type="hinton2017", recon=False, name="Pk Beutler 2017", postprocess=None, smooth=False):
        super().__init__(fix_params=fix_params, smooth_type=smooth_type, name=name, postprocess=postprocess, smooth=smooth)

        self.recon = recon

    def declare_parameters(self):
        super().declare_parameters()
        self.add_param("sigma_nl", r"$\Sigma_{nl}$", 0.01, 20.0, 10.0)  # BAO damping
        self.add_param("sigma_s", r"$\Sigma_s$", 0.01, 20.0, 10.0)  # Fingers-of-god damping
        self.add_param("a1", r"$a_1$", -50000.0, 50000.0, 0)  # Polynomial marginalisation 1
        self.add_param("a2", r"$a_2$", -50000.0, 50000.0, 0)  # Polynomial marginalisation 2
        self.add_param("a3", r"$a_3$", -50000.0, 50000.0, 0)  # Polynomial marginalisation 3
        self.add_param("a4", r"$a_4$", -1000.0, 1000.0, 0)  # Polynomial marginalisation 4
        self.add_param("a5", r"$a_5$", -10.0, 10.0, 0)  # Polynomial marginalisation 5

    def compute_power_spectrum(self, k, p, smooth=False):
        """ Computes the power spectrum for the Beutler et. al., 2017 model at k/alpha
        
        Parameters
        ----------
        k : np.ndarray
            Array of wavenumbers to compute
        p : dict
            dictionary of parameter names to their values
        smooth : bool, optional
            Whether to return a smooth model or not. Defaults to False
            
        Returns
        -------
        array
            pk_final - The power spectrum at the dilated k-values
        
        """

        # Get the basic power spectrum components
        ks = self.camb.ks
        pk_smooth_lin, pk_ratio = self.compute_basic_power_spectrum(p["om"])

        # Compute the propagator
        C = np.exp(-0.5*ks**2*p["sigma_nl"]**2)

        # Compute the smooth model
        fog = 1.0/(1.0 + ks**2*p["sigma_s"]**2/2.0)**2
        pk_smooth = p["b"]**2*pk_smooth_lin*fog

        # Polynomial shape
        if self.recon:
            shape = p["a1"] * ks**2 + p["a2"] + p["a3"] / ks + p["a4"] / (ks * ks) + p["a5"] / (ks ** 3)
        else:
            shape = p["a1"] * ks + p["a2"] + p["a3"] / ks + p["a4"] / (ks * ks) + p["a5"] / (ks ** 3)

        if smooth:
            pk_final = splev(k / p["alpha"], splrep(ks, pk_smooth + shape))
        else:
            pk_final = splev(k / p["alpha"], splrep(ks, (pk_smooth + shape)*(1.0 + pk_ratio*C)))

        return pk_final


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="[%(levelname)7s |%(funcName)20s]   %(message)s")
    logging.getLogger("matplotlib").setLevel(logging.ERROR)
    recon = True
    model1 = PowerBeutler2017(recon=recon, name=f"Beutler2017, recon={recon}")
    model_smooth = PowerBeutler2017(recon=recon, name=f"Beutler2017, recon={recon}", smooth=True)

    from barry.framework.datasets.mock_power import MockPowerSpectrum
    from barry.framework.datasets.dummy_power import DummyPowerSpectrum
    dataset1 = MockPowerSpectrum(name="Recon mean", recon=recon, min_k=0.02, max_k=0.3, reduce_cov_factor=30, step_size=3)
    dataset2 = DummyPowerSpectrum(name="Dummy data, real window fn", min_k=0.02, max_k=0.25, step_size=2, dummy_window=False)
    dataset3 = DummyPowerSpectrum(name="DummyWindowFnToo", min_k=0.02, max_k=0.25, step_size=2, dummy_window=True)
    data1 = dataset1.get_data()
    data2 = dataset2.get_data()
    data3 = dataset3.get_data()


    # model1.set_data(data1)
    # p, minv = model1.optimize()
    # print(p)
    # print(minv)
    # model1.plot(p)

    model1.set_fix_params(["om", "sigma_nl", "sigma_s"])
    model1.set_default("sigma_nl", 0.01)
    model1.set_default("sigma_s", 0.01)
    model_smooth.set_fix_params(["om", "sigma_nl", "sigma_s"])
    model_smooth.set_default("sigma_nl", 0.01)
    model_smooth.set_default("sigma_s", 0.01)

    # First comparison - the actual recon data
    # model1.set_data(data1)
    # p, minv = model1.optimize()
    # model_smooth.set_data(data1)
    # p2, minv2 = model_smooth.optimize()
    # print(p)
    # print(minv)
    # model1.plot(p, smooth_params=p2)


    # The second comparison, dummy data with real window function
    # model1.set_data(data2)
    # p, minv = model1.optimize()
    # model_smooth.set_data(data2)
    # p2, minv2 = model_smooth.optimize()
    # print(p)
    # print(minv)
    # model1.plot(p, smooth_params=p2)

    # Dummy data *and* dummy window function
    model1.set_data(data3)
    p, minv = model1.optimize()
    model_smooth.set_data(data3)
    p2, minv2 = model_smooth.optimize()
    print(p)
    print(minv)
    model1.plot(p, smooth_params=p2)

    if False:
        import timeit
        n = 100

        def test():
            model1.get_likelihood(p)

        print("Likelihood takes on average, %.2f milliseconds" % (timeit.timeit(test, number=n) * 1000 / n))

    if False:
        ks = data["ks"]
        pk = data["pk"]
        pk2 = model.get_model(data, p)
        model.smooth_type = "eh1998"
        pk3 = model.get_model(data, p)
        import matplotlib.pyplot as plt
        plt.errorbar(ks, pk, yerr=np.sqrt(np.diag(data["cov"])), fmt="o", c='k', label="Data")
        plt.plot(ks, pk2, '.', c='r', label="hinton2017")
        plt.plot(ks, pk3, '+', c='b', label="eh1998")
        plt.xlabel("k")
        plt.ylabel("P(k)")
        plt.xscale('log')
        plt.yscale('log')
        plt.legend()
        plt.show()

        model.smooth_type = "hinton2017"
        pk_smooth_lin, _ = model.compute_basic_power_spectrum(p["om"])
        pk_smooth_interp = splev(data["ks_input"], splrep(model.camb.ks, pk_smooth_lin))
        pk_smooth_lin_windowed, mask = model.adjust_model_window_effects(pk_smooth_interp)
        pk2 = model.get_model(data, p)
        import matplotlib.pyplot as plt
        plt.plot(ks, pk2/pk_smooth_lin_windowed[mask], '.', c='r', label="pre-recon")
        plt.xlabel("k")
        plt.ylabel(r"$P(k)/P_{sm}(k)$")
        plt.xscale('log')
        plt.yscale('log')
        plt.ylim(0.4, 3.0)
        plt.legend()
        plt.show()