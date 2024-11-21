import math
from scipy.optimize import curve_fit
from scipy.stats import kendalltau
from statsmodels.stats.multitest import multipletests
import pandas as pd
import numpy as np
from pycyclebio.pycyclebio import harmonic_oscillator, pseudo_square_wave, pseudo_cycloid_wave, transient_impulse

def fourier_square_wave(t, A, gamma, omega, phi,  y):

    return A * np.exp(gamma * t) * (1 + (4/math.pi)*np.sum(
        np.sin(math.pi*omega*(t+phi))+np.sin(math.pi*3*omega*(t+phi))/3)) + y

def fourier_cycloid_wave(t, A, gamma, omega, phi, y):
    return A * np.exp(gamma * t) * (2/math.pi - (4 / math.pi) * np.sum(
        np.cos(2* omega * (t + phi))/(3) + (np.cos( 4 * omega * (t + phi)) / (4*2^2-1)))) + y

def fourier_sawtooth_wave(t, A, gamma, omega, phi, y):
    return A * np.exp(gamma * t) * (0.5 - (1/math.pi)* np.sum(
        np.sin(2*math.pi*omega*(t+phi)) + np.sin(4*math.pi*omega*(t+phi))/2))



def calculate_variances(data):
    # Extract ZT times and replicate numbers from the column names
    zt_replicates = data.index.str.extract(r'(ZT\d+)_(C\d+)')
    zt_times = zt_replicates[0].str.extract(r'ZT(\d+)').astype(int)[0].values

    # Group by ZT times and calculate variances
    variances = {}
    for i, zt in enumerate(np.unique(zt_times)):
        # Find columns corresponding to this ZT time
        zt_columns = data.index[zt_times == zt]
        # Calculate variance across these columns, ignoring NaNs
        zt_var = data[zt_columns].var(ddof=1)
        variances[zt] = zt_var if zt_var else 0  # Replace NaN variances with 0
    return variances

def fit_best_waveform(df_row):
    """
    Fits all three waveform models to the data and determines the best fit.

    :param df_row: A DataFrame row containing the data to fit.
    :return: A tuple containing the best-fit parameters, the waveform type, and the covariance of the fit.
    """
    timepoints = np.array([float(col.split('_')[0][2:]) for col in df_row.index])
    timepoints = (timepoints /24 * (2 * math.pi)) # Todo: Consider introducing another term here for vairable period length (24 will only work for circ studies)
    amplitudes = df_row.values
    variances = calculate_variances(df_row)
    weights = np.array([1 / variances[tp] if tp in variances and variances[tp] != 0 else 0 for tp in timepoints])+0.000001 # 0 variance messes model selection up, so a negligable value is used here

    # Fit extended harmonic oscillator
    # (t, A, gamma, omega, phi, y):
    harmonic_initial_params = [np.median(amplitudes), 0, 1, 0, np.mean(amplitudes)/2]
    lower_bounds= [np.min(amplitudes), -0.05, 0.75, -(4*math.pi), -np.abs(amplitudes[np.argmax(np.abs(amplitudes))])] # (t, A, gamma, omega, phi, y):
    upper_bounds = [np.max(amplitudes), 0.05, 1.25, (4*math.pi), np.max(amplitudes)]
    harmonic_bounds = (lower_bounds, upper_bounds)
    try:
        harmonic_params, harmonic_covariance = curve_fit(
            harmonic_oscillator,
            timepoints,
            amplitudes,
            bounds=harmonic_bounds,
            sigma=weights,
            p0=harmonic_initial_params,
            maxfev=1000000,
            ftol = 0.001,
            xtol = 0.001
        )
        harmonic_fitted_values = harmonic_oscillator(timepoints, *harmonic_params)
        harmonic_residuals = amplitudes - harmonic_fitted_values
        harmonic_sse = np.sum(harmonic_residuals ** 2)
    except:
        harmonic_params = np.nan
        harmonic_covariance = np.nan
        harmonic_fitted_values = [0] * len(df_row)
        harmonic_sse = np.inf

    # Fit square oscillator
    # (t, A, gamma, omega, phi, y):
    square_initial_params = [np.median(amplitudes), 0, 1, 0, np.mean(amplitudes)]
    square_lower_bounds = [np.min(amplitudes), -0.05, 0.75, -(4*math.pi), -np.abs(amplitudes[np.argmax(np.abs(amplitudes))])]
    square_upper_bounds = [np.max(amplitudes), 0.05, 1.25, (4*math.pi), np.max(amplitudes)]
    square_bounds = (square_lower_bounds, square_upper_bounds)
    try:
        square_params, square_covariance = curve_fit(
            pseudo_square_wave,
            timepoints,
            amplitudes,
            bounds=square_bounds,
            sigma=weights,
            p0=square_initial_params,
            maxfev=1000000,
            ftol = 0.001,
            xtol = 0.001
        )
        square_fitted_values = pseudo_square_wave(timepoints, *square_params)
        square_residuals = amplitudes - square_fitted_values
        square_sse = np.sum(square_residuals ** 2)
    except:
        square_params = np.nan
        square_covariance = np.nan
        square_fitted_values = [0] * len(df_row)
        square_sse = np.inf

    # Fit cycloid oscillator
    # (t, A, gamma, omega, phi, y):
    cycloid_initial_params = [np.median(amplitudes), 0, 1, 0, np.mean(amplitudes)] # Don't need to provide t
    cycloid_lower_bounds = [-np.max(amplitudes), -0.05, 0.75, -(4*math.pi), -np.abs(amplitudes[np.argmax(np.abs(amplitudes))])]
    cycloid_upper_bounds = [np.max(amplitudes), 0.05, 1.25, (4*math.pi), np.max(amplitudes)]
    cycloid_bounds = (cycloid_lower_bounds, cycloid_upper_bounds)
    try:
        cycloid_params, cycloid_covariance = curve_fit(
            pseudo_cycloid_wave,
            timepoints,
            amplitudes,
            bounds = cycloid_bounds,
            sigma=weights,
            p0=cycloid_initial_params,
            maxfev=1000000,
            ftol = 0.001,
            xtol = 0.001
        )
        cycloid_fitted_values = pseudo_cycloid_wave(timepoints, *cycloid_params)
        cycloid_residuals = amplitudes - cycloid_fitted_values
        cycloid_sse = np.sum(cycloid_residuals ** 2)
    except:
        cycloid_params = np.nan
        cycloid_covariance = np.nan
        cycloid_fitted_values = [0] * len(df_row)
        cycloid_sse = np.inf

    # Fit transient oscillator
    #   (t, A, p, w, y):
    transient_initial_params = [np.median(amplitudes), 1, 1, np.min(amplitudes)]
    transient_lower_bounds = [np.min(amplitudes)/2, 0.1, 0.1, 0]  # (A, p, w, y) # Lower bounds of p and w need to be adjusted with experimental resolution (in extreme cases), if they are too small compared to measurements they will produce a flat line (trasnient occuring for very small duration between points) which breaks the statistical corrections
    transient_upper_bounds = [np.max(amplitudes), 24, 4, np.max(amplitudes)]
    transient_bounds = (transient_lower_bounds, transient_upper_bounds)
    try:
        transient_params, transient_covariance = curve_fit(
            transient_impulse,
            timepoints,
            amplitudes,
            bounds=transient_bounds,
            sigma=weights,
            p0=transient_initial_params,
            maxfev=1000000,
            ftol = 0.001,
            xtol = 0.001
        )
        transient_fitted_values = transient_impulse(timepoints, *transient_params)
        transient_residuals = amplitudes - transient_fitted_values
        transient_sse = np.sum(transient_residuals ** 2)
    except:
        transient_params = np.nan
        transient_covariance = np.nan
        transient_fitted_values = [0] * len(df_row)
        transient_sse = np.inf

    # Determine best fit
    sse_values = [harmonic_sse, square_sse, cycloid_sse, transient_sse]
    best_fit_index = np.argmin(sse_values)
    if sse_values == [np.inf, np.inf, np.inf, np.inf]:
        best_params = np.NaN
        best_waveform = 'unsolved'
        best_covariance = np.NaN
        best_fitted_values = np.NaN
    elif best_fit_index == 0:
        best_params = harmonic_params
        best_waveform = 'harmonic_oscillator'
        best_covariance = harmonic_covariance
        best_fitted_values = harmonic_fitted_values
    elif best_fit_index == 1:
        best_params = square_params
        best_waveform = 'square_waveform'
        best_covariance = square_covariance
        best_fitted_values = square_fitted_values
    elif best_fit_index == 2:
        best_params = cycloid_params
        best_waveform = 'cycloid'
        best_covariance = cycloid_covariance
        best_fitted_values = cycloid_fitted_values
    else:
        best_params = transient_params
        best_waveform = 'transient'
        best_covariance = transient_covariance
        best_fitted_values = transient_fitted_values
    return best_waveform, best_params, best_covariance, best_fitted_values

def categorize_rhythm(gamma):
    """
    Categorizes the rhythm based on the value of γ.

    :param gamma: The γ value from the fitted parameters.
    :return: A string describing the rhythm category.
    """
    if 0.15 >= gamma >= 0.03:
        return 'damped'
    elif -0.15 <= gamma <= -0.03:
        return 'forced'
    elif -0.03 <= gamma <= 0.03:
        return 'stable'
    else:
        return 'overexpressed' if gamma > 0.15 else 'repressed'

def variance_based_filtering(df, min_feature_variance=0.05):
    """Variance-based filtering of features
    Arguments:

    :param df (dataframe): dataframe containing molecules by row and samples by columns
    :param min_feature_variance (float): Minimum variance to include a feature in the analysis; default: 5%
    Returns:

    :return variant_df (DataFrame): DataFrame with variant molecules (variance > min_feature_variance)
    :return invariant_df (DataFrame): DataFrame with invariant molecules (variance <= min_feature_variance)
    """
    variances = df.var(axis=1)
    variant_df = df.loc[variances > min_feature_variance]
    invariant_df = df.loc[variances <= min_feature_variance]
    return variant_df, invariant_df

def get_pycycle(df_in):
    """
    Models expression data using 4 equations.

    :param df_in: A dataframe organised with samples defined by columns and molecules defined by rows.
                    The first column and row shuold contain strings identifying samples or molecules.
                    Samples should be organised in ascending time order (all reps per timepoint should be together)
    :return: df_out: A dataframe containing the best-fitting model, with parameters that produced the best fit,
                        alongside statistics indicating the robustness of the model's fit compared to input data.
    """
    df_in = df_in.set_index(df_in.columns[0])
    df, df_invariant = variance_based_filtering(df_in)  # Filtering removes invariant molecules from analysis
    pvals = []
    osc_type = []
    mod_type = []
    parameters = []
    if isinstance(df.iloc[0, 0], str):
        df = df.set_index(df.columns.tolist()[0])
    for i in range(df.shape[0]):
        waveform, params, covariance, fitted_values = fit_best_waveform(df.iloc[i, :])
        if waveform == 'unsolved':
            tau, p_value = np.NaN, np.NaN
            modulation = np.NaN
        else:
            tau, p_value = kendalltau(fitted_values, df.iloc[i, :].values)
            if waveform == 'transient':
                modulation = params[1]
            else:
                modulation = categorize_rhythm(params[1])
        oscillation = waveform
        if math.isnan(p_value):
            p_value = 1
        pvals.append(p_value)
        osc_type.append(oscillation)
        mod_type.append(modulation)
        parameters.append(params)
#        print(i)   # Uncomment this line for progress counter (will spam)
    corr_pvals = multipletests(pvals, alpha= 0.001, method='fdr_tsbh')[1] # alpha= 0.000001,
    df_out = pd.DataFrame({"Feature": df.index.tolist(), "p-val": pvals, "BH-padj": corr_pvals,"Type": osc_type, "Mod": mod_type, "parameters":parameters})
    invariant_features = df_invariant.index.tolist()
    invariant_rows = pd.DataFrame({
        "Feature": invariant_features,
        "p-val": [np.nan] * len(invariant_features),
        "BH-padj": [np.nan] * len(invariant_features),
        "Holm-padj": [np.nan] * len(invariant_features),
        "Type": ['invariant'] * len(invariant_features),
        "parameters": [np.nan] * len(invariant_features)
    })
    # Concatenate variant and invariant rows
    df_out = pd.concat([df_out, invariant_rows], ignore_index=False)
    return df_out.sort_values(by='p-val').sort_values(by='BH-padj')

# Todo: can fourier transformations be used to aid in parameterisation of waveforms?
# Todo: Introduce a term to allow wavelengths of different periods to be analysed
# Todo: tighten up time extraction, ZT phrasing unnecessary
# Todo: Cosinor also sums the composite eqns. can we use a eqn that multiplies components?
# Todo: Include compositional transforms + uncertainty scale model
# Todo: introduce modifier to y term (baseline) to capture general trends in expression?