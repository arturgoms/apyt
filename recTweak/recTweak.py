import numpy as np
import pandas as pd
import tensorflow as tf
tf.compat.v1.disable_v2_behavior()
print(tf.__version__)
from sklearn import preprocessing
from sklearn.metrics import precision_score

# Global variables
k = 10
generations = 50
display_step = 10
learning_rate = 0.4
batch_size = 250
train_data = "./ratings.dat"
test_data = "./test.dat"

# Reading dataset with the movies ratings for each user
df = pd.read_csv(train_data, sep='t', names=['user', 'item', 'rating', 'timestamp'], header=None)
df = df.drop('timestamp', axis=1)

num_items = df.item.nunique()
num_users = df.user.nunique()
print("USERS: {} ITEMS: {}".format(num_users, num_items))

# Normalize in [0, 1] to use the data in np matrix
r = df['rating'].values.astype(float)
min_max_scaler = preprocessing.MinMaxScaler()
x_scaled = min_max_scaler.fit_transform(r.reshape(-1,1))
df_normalized = pd.DataFrame(x_scaled)
df['rating'] = df_normalized

# Convert DataFrame in user-item matrix
matrix = df.pivot(index='user', columns='item', values='rating')
matrix.fillna(0, inplace=True)

# Users and items ordered as they are in matrix
users = matrix.index.tolist()
items = matrix.columns.tolist()
matrix = matrix.as_matrix()

# Network Parameters
num_input = num_items   # num of items
num_hidden_1 = 10       # 1st layer num features
num_hidden_2 = 5        # 2nd layer num features (the latent dim)

X = tf.placeholder(tf.float64, [None, num_input])

weights = {
    'encoder_h1': tf.Variable(tf.random_normal([num_input, num_hidden_1], dtype=tf.float64)),
    'encoder_h2': tf.Variable(tf.random_normal([num_hidden_1, num_hidden_2], dtype=tf.float64)),
    'decoder_h1': tf.Variable(tf.random_normal([num_hidden_2, num_hidden_1], dtype=tf.float64)),
    'decoder_h2': tf.Variable(tf.random_normal([num_hidden_1, num_input], dtype=tf.float64)),
}

bias = {
    'encoder_b1': tf.Variable(tf.random_normal([num_hidden_1], dtype=tf.float64)),
    'encoder_b2': tf.Variable(tf.random_normal([num_hidden_2], dtype=tf.float64)),
    'decoder_b1': tf.Variable(tf.random_normal([num_hidden_1], dtype=tf.float64)),
    'decoder_b2': tf.Variable(tf.random_normal([num_input], dtype=tf.float64)),
}


# Building the encoder

def encoder(x):
    # Encoder Hidden layer with sigmoid activation #1
    layer_1 = tf.nn.sigmoid(tf.add(tf.matmul(x, weights['encoder_h1']), bias['encoder_b1']))
    # Encoder Hidden layer with sigmoid activation #2
    layer_2 = tf.nn.sigmoid(tf.add(tf.matmul(layer_1, weights['encoder_h2']), bias['encoder_b2']))
    return layer_2


# Building the decoder

def decoder(x):
    # Decoder Hidden layer with sigmoid activation #1
    layer_1 = tf.nn.sigmoid(tf.add(tf.matmul(x, weights['decoder_h1']), bias['decoder_b1']))
    # Decoder Hidden layer with sigmoid activation #2
    layer_2 = tf.nn.sigmoid(tf.add(tf.matmul(layer_1, weights['decoder_h2']), bias['decoder_b2']))
    return layer_2


# Construct model
encoder_op = encoder(X)
decoder_op = decoder(encoder_op)

# Prediction
y_pred = decoder_op

# Targets are the input data.
y_true = X

# Define loss and optimizer, minimize the squared error
loss = tf.losses.mean_squared_error(y_true, y_pred)
# Using the RMSProp optimizer
optimizer = tf.train.RMSPropOptimizer(learning_rate).minimize(loss)
# I Try with adam optimizer but the calculations for each movie stays the same, 
# That is not the result that we want because for each user that movie needs a probability of like

predictions = pd.DataFrame()

# Define evaluation metrics, whe dont have a exact number of inputs
eval_x = tf.placeholder(tf.int32, )
eval_y = tf.placeholder(tf.int32, )
pre, pre_op = tf.metrics.precision(labels=eval_x, predictions=eval_y)


# Initialize the variables (i.e. assign their default value)
init = tf.global_variables_initializer()
local_init = tf.local_variables_initializer()

with tf.Session() as session:
    session.run(init)
    session.run(local_init)

    num_batches = int(matrix.shape[0] / batch_size)
    matrix = np.array_split(matrix, num_batches)

    for i in range(generations):

        avg_cost = 0

        for batch in matrix:
            _, l = session.run([optimizer, loss], feed_dict={X: batch})
            avg_cost += l

        avg_cost /= num_batches

        print("Generation: {} Error: {}".format(i + 1, avg_cost))

    print("Predictions...")

    matrix = np.concatenate(matrix, axis=0)
    preds = session.run(decoder_op, feed_dict={X: matrix})
    predictions = predictions.append(pd.DataFrame(preds))
    predictions = predictions.stack().reset_index(name='rating')
    predictions.columns = ['user', 'item', 'rating']
    predictions['user'] = predictions['user'].map(lambda value: users[value])
    predictions['item'] = predictions['item'].map(lambda value: items[value])

    print("Filtering out items in training set")

    keys = ['user', 'item']
    i1 = predictions.set_index(keys).index
    i2 = df.set_index(keys).index
    recs = predictions[~i1.isin(i2)]
    recs = recs.sort_values(['user', 'rating'], ascending=[True, False])
    recs = recs.groupby('user').head(k)
    recs.to_csv('recs.tsv', sep='\t', index=False, header=False)

    # create a vector where there are for each user his own 10 movies recommendations
    test = pd.read_csv(test_data, sep='t', names=['user', 'item', 'rating', 'timestamp'], header=None)
    test = test.drop('timestamp', axis=1)
    test = test.sort_values(['user', 'rating'], ascending=[True, False])

    print("Evaluating...")

    p = 0.0
    for user in users[:10]:
        test_list = test[(test.user == user)].head(k).as_matrix(columns=['item']).flatten()
        recs_list = recs[(recs.user == user)].head(k).as_matrix(columns=['item']).flatten()
        session.run(pre_op, feed_dict={eval_x: test_list, eval_y: recs_list})

        pu = precision_score(test_list, recs_list, average='micro')
        p += pu

        movies = pd.read_csv('./movies.dat', sep=';', names=['id', 'name', 'category'], header=None)
        print('For the user: {}'.format(user))
        print('Movies with the best ratings for this user:')
        for movie in test_list:
            # Getting the rating for that movie
            rating = 0
            user_a = test[test['user'] == user]
            for userN in user_a.values:
                user_n = list(userN)
                if user_n[1] == movie:
                    rating = user_n[2]
            print('Movie: {}, Category: {}, Rating: {} stars'.format(movies.values[movie][1], movies.values[movie][2], rating))

        print('We recommend this films:')
        for movie in recs_list:
            # Getting the rating for that movie
            rating = 0
            user_a = recs[recs['user'] == user]
            for userN in user_a.values:
                user_n = list(userN)
                if user_n[1] == movie:
                    rating = user_n[2]
            print('Movie: {}, Category: {}, Probability of like: {}% '.format(movies.values[movie][1], movies.values[movie][2], round(rating*100, 2)))