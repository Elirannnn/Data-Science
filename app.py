from flask import Flask, render_template, request, jsonify, send_file, url_for
from flask_cors import CORS
import os
import pandas as pd
import re
import tempfile

app = Flask(__name__)
CORS(app)

# פונקציית עיבוד הנתונים
def clean_and_sort_data(input_file, allocations, weight_unit):
    weight_soldier = 1 - weight_unit  # משלים את האחוז ליחידה
    df = pd.read_excel(input_file)
    cleaned_data = []

    for _, row in df.iterrows():
        soldier_name = row['שם החייל']
        city = row['עיר מגורים']
        unit_ratings = row['יחידות ודירוגים']
        unit_rating_pairs = unit_ratings.split('\n')

        for priority, unit_rating in enumerate(unit_rating_pairs, start=1):
            match = re.match(r"(.*)\((\d+)\)", unit_rating)
            if match:
                unit_name = match.group(1).strip()
                unit_score = int(match.group(2))
                average_score = (weight_unit * unit_score) + (weight_soldier * (8 - priority))
                cleaned_data.append({
                    'שם החייל': soldier_name,
                    'עיר מגורים': city,
                    'יחידה': unit_name,
                    'דירוג החייל': 8 - priority,
                    'דירוג היחידה': unit_score,
                    'ממוצע': average_score
                })

    cleaned_df = pd.DataFrame(cleaned_data)
    cleaned_df = cleaned_df.sort_values(by='ממוצע', ascending=False)
    assignments = []

    total_rounds = max(allocations.values())
    for round_number in range(total_rounds):
        used_units = set()
        for _, row in cleaned_df.iterrows():
            soldier_name = row['שם החייל']
            city = row['עיר מגורים']
            unit_name = row['יחידה']
            soldier_rating = row['דירוג החייל']
            unit_rating = row['דירוג היחידה']
            if allocations.get(unit_name, 0) > 0 and unit_name not in used_units:
                assignments.append({
                    'שם החייל': soldier_name,
                    'עיר מגורים': city,
                    'יחידה': unit_name,
                    'דירוג החייל': soldier_rating,
                    'דירוג היחידה': unit_rating
                })
                allocations[unit_name] -= 1
                used_units.add(unit_name)
        cleaned_df = cleaned_df[~cleaned_df['שם החייל'].isin([a['שם החייל'] for a in assignments])]
        if cleaned_df.empty:
            break

    assignments_df = pd.DataFrame(assignments)

    if not assignments_df.empty:
        assigned_unit_avg = assignments_df.groupby('יחידה')['דירוג היחידה'].mean().reset_index()
        assigned_unit_avg.columns = ['יחידה', 'ממוצע']

        assignments_df = assignments_df.merge(assigned_unit_avg, on='יחידה', how='left')
        assignments_df = assignments_df.sort_values(by='יחידה', ascending=True)

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    assignments_df.to_excel(temp_file.name, index=False)

    return assignments_df.to_dict(orient='records'), temp_file.name


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        weight_unit = float(request.form['weight_unit']) / 100  # המרה לאחוז
        allocations = {
            'הנדסה': int(request.form['הנדסה']),
            'מאב': int(request.form['מאב']),
            'מהן': int(request.form['מהן']),
            'מעמ': int(request.form['מעמ']),
            'מתן': int(request.form['מתן']),
            'מטס': int(request.form['מטס']),
            'תשתיות': int(request.form['תשתיות'])
        }

        file = request.files['file']
        if file:
            input_file = os.path.join('uploads', file.filename)
            os.makedirs('uploads', exist_ok=True)
            file.save(input_file)

            assignments, temp_file_path = clean_and_sort_data(input_file, allocations, weight_unit)
            return render_template('index.html', assignments=assignments, temp_file=temp_file_path, weight_unit=int(weight_unit * 100))

    return render_template('index.html', weight_unit=80)  # ברירת מחדל

@app.route('/download', methods=['GET'])
def download_file():
    temp_file = request.args.get('path')
    if temp_file and os.path.exists(temp_file):
        return send_file(temp_file, as_attachment=True)
    else:
        return jsonify({'error': 'File not found'}), 404


if __name__ == '__main__':
    app.run(debug=True)
